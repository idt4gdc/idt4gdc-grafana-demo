import os
import sys
import contextlib

@contextlib.contextmanager
def suppress_output():
    with open(os.devnull, 'w') as fnull:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = fnull
        sys.stderr = fnull
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

with suppress_output():
    from ortools.sat.python import cp_model

def estimate_duration(job):
    return job["int_cycles"] if job["mode"] == "CPU" else job["float_cycles"]


def cast_to_int(ts):
    return list(map(lambda v: round(v), ts))


def schedule_jobs(data_centres, jobs):
    model = cp_model.CpModel()

    num_dcs = len(data_centres)
    total_jobs = len(jobs)  # Number of jobs to schedule

    # Decision variables
    x = []  # x[d][j][i]: Whether job j in data-centre d starts at time-period i
    job_start_times = []  # Variable to track job start times

    for d in range(num_dcs):
        total_length = len(data_centres[d]["forecasted_ci"])
        x.append([[model.NewBoolVar(f'x_{d}_{j}_{i}') for i in range(total_length - estimate_duration(jobs[j]) + 1)]
                  for j in range(total_jobs)])

    for s in range(total_jobs):
        job_start_times.append(model.NewIntVar(0, max(len(dc["forecasted_ci"]) for dc in data_centres) - 1, f'start_time_{s}'))

    # Constraints: Each job must start exactly once in a data-centre
    for s in range(total_jobs):
        if "data_centre" in jobs[s] and "start_time" in jobs[s]:
            d = jobs[s]["data_centre"]
            start_time = jobs[s]["start_time"]
            model.Add(x[d][s][start_time] == 1)
            model.Add(job_start_times[s] == start_time)

        model.Add(sum(x[l][s][i] for l in range(num_dcs) for i in range(len(data_centres[l]["forecasted_ci"]) - estimate_duration(jobs[s]) + 1)) == 1)

        # Link start time variable to actual start slot via OnlyEnforceIf
        # (replaces AddMinEquality which incorrectly yields 0 when unset slots dominate)
        for l in range(num_dcs):
            for i in range(len(data_centres[l]["forecasted_ci"]) - estimate_duration(jobs[s]) + 1):
                model.Add(job_start_times[s] == i).OnlyEnforceIf(x[l][s][i])

        # Optional scheduling window (slot indices relative to horizon)
        if "window_start" in jobs[s]:
            ws = max(0, jobs[s]["window_start"])
            for l in range(num_dcs):
                for i in range(min(ws, len(data_centres[l]["forecasted_ci"]) - estimate_duration(jobs[s]) + 1)):
                    model.Add(x[l][s][i] == 0)
        if "window_end" in jobs[s]:
            we = jobs[s]["window_end"]
            for l in range(num_dcs):
                for i in range(we + 1, len(data_centres[l]["forecasted_ci"]) - estimate_duration(jobs[s]) + 1):
                    model.Add(x[l][s][i] == 0)

    # Ensure jobs do not exceed resource availability in each data-centre
    for d in range(num_dcs):
        ci_length = len(data_centres[d]["forecasted_ci"])
        available_cpus = data_centres[d]["available_cpus"]
        available_gpus = data_centres[d]["available_gpus"]

        for i in range(ci_length):
            overlapping_cpu_jobs = []
            overlapping_gpu_jobs = []
            for s in range(total_jobs):
                job_mode = jobs[s]["mode"]  # 'CPU' or 'GPU'
                rc = jobs[s].get("resource_count", 1)
                for j in range(max(0, i - estimate_duration(jobs[s]) + 1), min(i + 1, ci_length - estimate_duration(jobs[s]) + 1)):
                    if job_mode == "CPU":
                        overlapping_cpu_jobs.append(rc * x[d][s][j])
                    else:
                        overlapping_gpu_jobs.append(rc * x[d][s][j])
            if overlapping_cpu_jobs:
                model.Add(sum(overlapping_cpu_jobs) <= available_cpus)
            if overlapping_gpu_jobs:
                model.Add(sum(overlapping_gpu_jobs) <= available_gpus)

    # Compute estimated carbon-intensity sums
    carbon_intensity_sums = [model.NewIntVar(0, sum(sum(lst["forecasted_ci"]) for lst in data_centres), f'carbon_{s}_sum') for s in range(total_jobs)]
    electricity_cost_sums = [model.NewIntVar(0, sum(sum(lst["forecasted_price"]) for lst in data_centres), f'cost_{s}_sum') for s in range(total_jobs)]

    for s in range(total_jobs):
        carbon_sum_expr = sum(
            data_centres[l]["forecasted_ci"][j] * x[l][s][i]
            for l in range(num_dcs)
            for i in range(len(data_centres[l]["forecasted_ci"]) - estimate_duration(jobs[s]) + 1)
            for j in range(i, min(i + estimate_duration(jobs[s]), len(data_centres[l]["forecasted_ci"])))
        )
        model.Add(carbon_intensity_sums[s] == carbon_sum_expr)

        cost_sum_expr = sum(
            data_centres[l]["forecasted_price"][j] * x[l][s][i]
            for l in range(num_dcs)
            for i in range(len(data_centres[l]["forecasted_price"]) - estimate_duration(jobs[s]) + 1)
            for j in range(i, min(i + estimate_duration(jobs[s]), len(data_centres[l]["forecasted_price"])))
        )
        model.Add(electricity_cost_sums[s] == cost_sum_expr)

    # Objective: Minimize total weighted carbon intensity and prioritize earlier start times
    model.Minimize(
        sum(
            carbon_intensity_sums[s] * jobs[s]["carbon_weight"] +
            electricity_cost_sums[s] * jobs[s]["cost_weight"] +
            job_start_times[s] * jobs[s]["priority"]
            for s in range(total_jobs)
        )
    )

    # Solve the model
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        results = []
        for s in range(total_jobs):
            for d in range(num_dcs):
                for i in range(len(data_centres[d]["forecasted_ci"]) - estimate_duration(jobs[s]) + 1):
                    if solver.Value(x[d][s][i]) == 1:
                        ci_splice = data_centres[d]["forecasted_ci"][i:min(i + estimate_duration(jobs[s]), len(data_centres[d]["forecasted_ci"]))]
                        cost_splice = data_centres[d]["forecasted_price"][i:min(i + estimate_duration(jobs[s]), len(data_centres[d]["forecasted_price"]))]
                        results.append((d, i, ci_splice, sum(ci_splice), cost_splice, sum(cost_splice), jobs[s]["priority"], jobs[s]["mode"]))
        return results
    else:
        return None


# int_cycles - duration for execution on CPU
# float_cycles - duration for execution on GPU
# -> estimated duration