# Listing helper

Fills the insurance-housing landlord sign-up forms in a real Chrome window.
It never submits: you review each form and click Submit yourself.

## Setup (once)

    cd tools/listings
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    cp property.example.yaml property.yaml   # then fill in every TODO

Uses your installed Google Chrome. Logins are kept in `.profile/` between runs.

## Run

    .venv/bin/python submit.py --list          # site keys
    .venv/bin/python submit.py all             # every insurance site, one tab at a time
    .venv/bin/python submit.py ale dvg         # just these
    .venv/bin/python submit.py zillow          # opens Zillow + prints values to paste

| Key | Site | Filled automatically |
|---|---|---|
| ale | ALE Solutions | Everything except the ownership checkbox |
| dvg | De La Ville Group (DVG) | Everything except the consent checkbox |
| shelterpoint | Shelter Point Solutions | Everything plus 20 photos; you tick utilities, source, authorization |
| oem | OEM Properties | Everything plus 10 photos |
| alehousing | ALE Housing (free intake form) | Everything |
| sedgwick | Sedgwick | Email only (multi-step HubSpot form) |
| crs | CRS Temporary Housing | Nothing (SurveyMonkey); values printed to paste |
| zillow | Zillow Rental Manager | Nothing; values and photo folder printed |
