# Tezcatlipoca — quarantine of non-approved hosted APIs (2026-11-10)

This change does not delete domain engines, stored data, BIM, market research, or the real catalogues. It disables **runtime use** of hosted services without a verified free commercial licence. It does not assert that the providers are illegal or that a paid licence could not be obtained.

## Blocked / replacement required

| Provider | Existing integration | Replacement capability | Reason |
| --- | --- | --- | --- |
| OpenSky | `DataFetcherEngine.fetch_opensky` | ADS-B flights | Commercial/operational use requires written licence |
| ADS-B Exchange | `/aviation/adsb/*` | ADS-B positions and GPS interference inputs | Commercial API licence |
| Open-Meteo hosted | `DataFetcherEngine.fetch_nws` | Weather/forecast | Hosted free API non-commercial |
| Google Earth Engine | `/sar/gee/*` | SAR/remote sensing | Commercial account and billing |
| GraphHopper hosted | `/transport/route`, `/transport/isochrone` | Routing/isochrones | Free tier not cleared for production commercial use |
| Shodan | `/cyber/shodan/*` | Device/exposure intelligence | Paid API features |
| Censys Free | `/cyber/censys/*` | Certificate/host intelligence | Free plan expressly prohibits commercial use |
| GreyNoise Free | `/cyber/greynoise/*` | IP threat intelligence | Free access not approved for product redistribution |
| AVWX hosted | `/aviation/metar/*`, `/aviation/taf/*` | METAR/TAF | Free tier scope not yet approved for the product |

**Scope of this commit:** blocked HTTP routes in the Megalodon runtime and removed scheduled OpenSky/Open-Meteo requests. The old adapters remain in source for comparison and replacement. Some other consumers, alternative runtime paths, or secondary provider calls may still need review before declaring the entire product licence-clean. Do not use this commit alone as legal compliance certification.

**Still under review, not automatically approved:** AISstream, adsb.lol, AVWX, OpenAQ, GTFS/rail providers and any provider whose redistribution or commercial terms have not been verified. Keep these outside commercial release until reviewed.

**Keep:** public USGS, NASA public datasets, Sentinel/Copernicus datasets under their own attribution rules, CISA KEV and open-source processing engines. Open-source code does not mean a hosted API is free for commercial use. Self-hosting can entail software obligations and infrastructure cost.

Official terms: https://opensky-network.org/about/terms-of-use ; https://open-meteo.com/en/pricing ; https://developers.google.com/earth-engine/guides/transition_to_commercial ; https://www.graphhopper.com/terms/ ; https://censys.com/terms-of-service/ ; https://www.greynoise.io/terms ; https://support.adsbexchange.com/hc/en-us/articles/37363886073613-I-m-building-a-project-for-my-company-but-we-aren-t-making-money-off-of-it-can-I-get-a-free-API-key
