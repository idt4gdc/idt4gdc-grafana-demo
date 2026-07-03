import requests


def get_intensity_data(_from, postcode, period=24):
    headers = {
        'Accept': 'application/json'
    }
    r = requests.get(f'https://api.carbonintensity.org.uk/regional/intensity/{_from}/fw{period}h/postcode/{postcode}', params={}, headers=headers)
    return r.json()
