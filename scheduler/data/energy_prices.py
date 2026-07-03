import requests
import pandas as pd

def get_tariff_rates(region_code, product_code="AGILE-24-10-01"):
    tariff_code = f"E-1R-{product_code}-{region_code}"
    url = f"https://api.octopus.energy/v1/products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates/?page_size=48"

    response = requests.get(url)
    data = response.json()

    rates = [
        {
            "from": pd.to_datetime(entry["valid_from"]),
            "to": pd.to_datetime(entry["valid_to"]),
            "price_p_per_kwh": entry["value_inc_vat"]
        }
        for entry in data["results"]
    ]

    df = pd.DataFrame(rates)

    return df.sort_values("from").reset_index(drop=True)
