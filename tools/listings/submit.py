"""Fill insurance-housing landlord sign-up forms from property.yaml.

Opens a real Chrome window, fills each form, then stops. You review the form
and click Submit yourself; nothing is ever submitted by this script.

    python submit.py --list
    python submit.py ale dvg shelterpoint
    python submit.py all
"""
import argparse
import sys
from pathlib import Path

import yaml
from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
IMG = HERE.parent.parent / "img"
PROFILE = HERE / ".profile"
PHOTO_CACHE = HERE / "photos"


def load():
    path = HERE / "property.yaml"
    if not path.exists():
        sys.exit("Copy property.example.yaml to property.yaml and fill it in first.")
    return yaml.safe_load(path.read_text())


def val(v):
    """Treat TODO and blanks as missing."""
    if v is None or (isinstance(v, str) and v.strip() in ("", "TODO")):
        return None
    return v


def yesno(v):
    v = val(v)
    return None if v is None else ("Yes" if v else "No")


def mmddyyyy(iso):
    iso = val(iso)
    if not iso:
        return None
    y, m, d = str(iso).split("-")
    return f"{m}/{d}/{y}"


def photo_files(cfg, limit=20):
    """JPEG copies of the chosen photos; many forms reject webp."""
    PHOTO_CACHE.mkdir(exist_ok=True)
    out = []
    for i, name in enumerate(cfg["photos"][:limit], 1):
        dst = PHOTO_CACHE / f"{i:02d}-{name}.jpg"
        if not dst.exists():
            Image.open(IMG / f"{name}.webp").convert("RGB").save(dst, "JPEG", quality=85)
        out.append(str(dst))
    return out


class Form:
    """Small helpers that skip missing values and cope with hidden inputs."""

    def __init__(self, page):
        self.page = page

    def put(self, sel, value):
        value = val(value)
        if value is None:
            return
        loc = self.page.locator(sel).first
        try:
            if loc.is_visible():
                loc.fill(str(value))
                return
        except Exception:
            pass
        loc.evaluate(
            "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true}));"
            " el.dispatchEvent(new Event('change', {bubbles:true})); }",
            str(value),
        )

    def pick(self, sel, label):
        """Select by option text; exact match first, then prefix ("CA" -> "CA — California")."""
        label = val(label)
        if label is None:
            return
        found = self.page.locator(sel).first.evaluate(
            """(el, want) => {
                const opts = [...el.options];
                const o = opts.find(o => o.text.trim() === want)
                       || opts.find(o => o.text.trim().startsWith(want));
                if (!o) return false;
                el.value = o.value;
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                return true;
            }""",
            str(label),
        )
        if not found:
            print(f"   ! no option '{label}' for {sel}")

    def lookup(self, sel, text):
        """Type into a Google Places box and take the first suggestion."""
        loc = self.page.locator(sel).first
        loc.click()
        loc.press_sequentially(text, delay=40)
        try:
            self.page.wait_for_selector(".pac-item", state="visible", timeout=6000)
            loc.press("ArrowDown")
            loc.press("Enter")
            self.page.wait_for_timeout(800)
        except Exception:
            print(f"   ! no address suggestion for {sel}; pick it by hand")

    def check(self, sel, on=True):
        if on:
            self.page.locator(sel).first.check(force=True)

    def upload(self, sel, files):
        if files:
            self.page.locator(sel).first.set_input_files(files)


# ---------------------------------------------------------------- sites

def ale_solutions(page, cfg):
    o, p, t = cfg["owner"], cfg["property"], cfg["terms"]
    page.goto("https://www.alesolutions.com/register-housing/", wait_until="domcontentloaded")
    page.wait_for_selector("#landlordFirstName")
    f = Form(page)
    f.put("#landlordFirstName", o["first_name"])
    f.put("#landlordLastName", o["last_name"])
    f.put("#landlordEmail", o["email"])
    f.put("#landlordPhone", o["phone"])
    f.put("#landlordCell", o["phone"])
    f.put("#landlordAddress", val(o.get("mailing_address")) or p["address"])
    f.put("#landlordCity", val(o.get("mailing_city")) or p["city"])
    f.pick("#landlordState", val(o.get("mailing_state")) or p["state"])
    f.put("#landlordZip", val(o.get("mailing_zip")) or p["zip"])
    f.pick("#housingType", "Single Family Home")
    full = f"{p['address']}, {p['city']}, {p['state']} {p['zip']}"
    f.lookup("#autoCompleteProperty", full)
    if not val(o.get("mailing_address")):
        f.lookup("#autoCompleteLandlord", full)
    f.put("#propertyAddress", p["address"])
    f.put("#propertyCity", p["city"])
    f.pick("#propertyState", p["state"])
    f.put("#propertyZip", p["zip"])
    f.put("#rent", t["monthly_rent"])
    f.pick("#minLease", f"{t['min_lease_months']} month" if t["min_lease_months"] == 1 else f"{t['min_lease_months']} months")
    f.put("#securityDeposit", t["deposit"])
    f.put("#dateAvailable", mmddyyyy(t["available_date"]))
    f.pick("#numBedrooms", "5+" if p["bedrooms"] >= 5 else str(p["bedrooms"]))
    f.pick("#numBaths", "5.0+" if p["bathrooms"] >= 5 else f"{float(p['bathrooms']):.1f}")
    f.put("#squareFootage", p["sqft"])
    f.pick("#parking", "Driveway")
    f.put("#website", cfg["site_url"])
    f.put("#schoolDistrict", p["school_district"])
    pets = val(t["pets_allowed"])
    if pets is not None:
        f.check("#petsAllowed-yes" if pets else "#petsAllowed-no")
        f.check("#pets5" if pets else "#pets1")
    f.check("#furnished-yes" if p["furnished"] else "#furnished-no")
    for a in ("#appliances1", "#appliances5", "#appliances4", "#appliances3", "#appliances2"):
        f.check(a)
    f.check("#a7")   # fenced yard
    f.check("#a8")   # balcony / deck
    f.check("#a11")  # swimming pool
    f.check("#a17")  # walk-in shower
    f.check("#a15", bool(val(t["utilities_included"])))
    f.check("#inUnit")
    f.check("#flooring2")
    f.put("#notes", cfg["text"]["full"] + "\n\n" + cfg["site_url"])
    print("   Tick the ownership acknowledgement box yourself.")


def dvg(page, cfg):
    o, p, t = cfg["owner"], cfg["property"], cfg["terms"]
    page.goto("https://delavillegroup.com/submit-property", wait_until="domcontentloaded")
    page.wait_for_selector("#first_name")
    f = Form(page)
    f.put("#first_name", o["first_name"])
    f.put("#last_name", o["last_name"])
    f.put("#phone", o["phone"])
    f.put("#email", o["email"])
    f.put("#address", p["address"])
    f.put("#city", p["city"])
    f.pick("#state", p["state"])
    f.put("#zip", p["zip"])
    f.put("#school_district", p["school_district"])
    f.pick("#property_type", "Single family home")
    f.pick("#furnished", yesno(p["furnished"]))
    f.put("#bedrooms", p["bedrooms"])
    f.put("#bathrooms", p["bathrooms"])
    f.put("#square_footage", p["sqft"])
    f.put("#max_occupancy", p["max_occupancy"])
    f.put("#parking", "Driveway, parking for 20+ vehicles")
    f.put("#laundry", p["laundry"])
    f.pick("#utilities_included", yesno(t["utilities_included"]))
    f.pick("#internet_included", yesno(t["internet_included"]))
    f.put("#min_lease_term", "Month-to-month")
    f.put("#amenities", cfg["text"]["amenities"])
    f.pick("#pets_allowed", yesno(t["pets_allowed"]))
    f.put("#pet_fee", t["pet_fee"])
    f.put("#monthly_rent", t["monthly_rent"])
    f.put("#deposit", t["deposit"])
    f.put("#cleaning_fee", t["cleaning_fee"])
    f.put("#other_listing_url", cfg["site_url"])
    f.put("#notes", cfg["text"]["full"])


def shelterpoint(page, cfg):
    o, p, t = cfg["owner"], cfg["property"], cfg["terms"]
    page.goto("https://shelterpointsolutions.com/partner-with-us.html", wait_until="domcontentloaded")
    n = lambda name: f'[name="{name}"]'
    page.wait_for_selector(n("Full name"))
    f = Form(page)
    f.put(n("Full name"), f"{val(o['first_name']) or ''} {val(o['last_name']) or ''}".strip())
    f.put(n("Phone"), o["phone"])
    f.put(n("Email"), o["email"])
    f.pick(n("I am the…"), "Property owner")
    f.put(n("Street address"), p["address"])
    f.put(n("City"), p["city"])
    f.put(n("ZIP code"), p["zip"])
    f.pick(n("County"), p["county"])
    f.pick(n("Property type"), "Single-family home")
    f.pick(n("Bedrooms"), "5+" if p["bedrooms"] >= 5 else str(p["bedrooms"]))
    f.pick(n("Bathrooms"), "4+" if p["bathrooms"] >= 4 else str(p["bathrooms"]))
    f.put(n("Approx. square feet"), p["sqft"])
    f.put(n("How many units are you submitting?"), 1)
    f.pick(n("Furnished?"), "Fully furnished" if p["furnished"] else "Unfurnished")
    f.pick(n("Laundry"), p["laundry"])
    f.pick(n("Air conditioning"), p["air_conditioning"])
    f.pick(n("Parking"), "Driveway")
    if val(t["pets_allowed"]) is False:
        f.check(n("Pets allowed? - No pets"))
    for extra in ("Private yard", "Pool", "Dishwasher"):
        f.check(n(f"Also has (check any) - {extra}"))
    f.put(n("Available starting"), t["available_date"])
    f.pick(n("Shortest stay you'd accept"), "1 month")
    f.put(n("Asking monthly rent"), t["monthly_rent"])
    f.upload(n("Attach photos of the home[]"), photo_files(cfg, 20))
    f.put(n("Or share a link to photos or a listing"), cfg["site_url"])
    f.put(n("Notes about the home"), cfg["text"]["full"])
    print("   Utilities checkboxes, how-did-you-hear and the authorization box are left for you.")


def oem(page, cfg):
    o, p, t = cfg["owner"], cfg["property"], cfg["terms"]
    page.goto("https://www.oemproperties.org/partners.html#property-submission", wait_until="domcontentloaded")
    page.wait_for_selector("#rf-name")
    f = Form(page)
    f.put("#rf-name", f"{val(o['first_name']) or ''} {val(o['last_name']) or ''}".strip())
    f.put("#rf-phone", o["phone"])
    f.put("#rf-email", o["email"])
    f.put("#rf-location", f"{p['city']}, {p['state']}")
    f.pick("#rf-beds", "5+" if p["bedrooms"] >= 5 else str(p["bedrooms"]))
    f.pick("#rf-baths", "3+" if p["bathrooms"] >= 3 else str(p["bathrooms"]))
    f.put("#rf-date", mmddyyyy(t["available_date"]))
    f.upload("#property-photos", photo_files(cfg, 10))
    f.put("#rf-summary", cfg["text"]["full"] + "\n\n" + cfg["site_url"])
    page.locator("#rf-name").scroll_into_view_if_needed()


def ale_housing(page, cfg):
    o, p, t = cfg["owner"], cfg["property"], cfg["terms"]
    page.goto("https://alehousing.com/landlords", wait_until="domcontentloaded")
    page.wait_for_selector('[name="full_name"]')
    f = Form(page)
    f.put('[name="full_name"]', f"{val(o['first_name']) or ''} {val(o['last_name']) or ''}".strip())
    f.put('form:has([name="full_name"]) [name="email"]', o["email"])
    f.put('[name="phone"]', o["phone"])
    f.pick('[name="property_type"]', "Single Family Home")
    f.pick('[name="bedrooms"]', f"{p['bedrooms']} bedrooms")
    f.pick('[name="bathrooms"]', f"{p['bathrooms']} baths")
    occ = val(p["max_occupancy"])
    if occ:
        f.pick('[name="max_guests"]', f"{occ} guests")
    f.put('[name="property_address"]', f"{p['address']}, {p['city']}, {p['state']} {p['zip']}")
    if p["furnished"]:
        page.get_by_label("Yes, fully furnished").check(force=True)
    f.put('[name="available_from"]', t["available_date"])
    f.put('[name="notes"]', cfg["text"]["short"] + " " + cfg["site_url"])
    page.locator('[name="full_name"]').scroll_into_view_if_needed()
    print("   This is the free intake form. The $25/month host program (myrealsync.com) is separate.")


def sedgwick(page, cfg):
    page.goto("https://www.sedgwick.com/temporary-housing/temporary-housing-directory/#contact",
              wait_until="domcontentloaded")
    # the HubSpot form only loads once it scrolls into view
    page.mouse.wheel(0, 20000)
    try:
        page.wait_for_selector('input[name="0-1/email"]', timeout=20000)
        Form(page).put('input[name="0-1/email"]', cfg["owner"]["email"])
        page.locator('input[name="0-1/email"]').scroll_into_view_if_needed()
        print("   HubSpot form with several steps: email is filled, continue through the steps by hand.")
    except Exception:
        print("   The form did not load automatically. Scroll to 'Submit your property' and fill it by hand.")
    cheat_sheet(cfg)


def crs(page, cfg):
    page.goto("https://crs.surveymonkey.com/r/CRSLandlordSurvey", wait_until="domcontentloaded")
    print("   SurveyMonkey survey, filled by hand. Values to copy:")
    cheat_sheet(cfg)
    print("   After the survey CRS offers paid Preferred Provider enrollment. That is optional.")


def zillow(page, cfg):
    page.goto("https://www.zillow.com/rental-manager/properties/add", wait_until="domcontentloaded")
    folder = Path(photo_files(cfg, 50)[0]).parent
    print("   Zillow is filled by hand (it blocks automation). Values to copy:")
    cheat_sheet(cfg)
    print(f"   Photos in upload order: {folder}")
    print("   Description: copy text.full from property.yaml.")
    print("   When it's live, put the listing URL in DVG's 'Zillow listing' field.")


def cheat_sheet(cfg):
    o, p, t = cfg["owner"], cfg["property"], cfg["terms"]
    rows = [
        ("Name", f"{o['first_name']} {o['last_name']}"), ("Email", o["email"]), ("Phone", o["phone"]),
        ("Address", f"{p['address']}, {p['city']}, {p['state']} {p['zip']}"),
        ("Beds / baths / sqft", f"{p['bedrooms']} / {p['bathrooms']} / {p['sqft']}"),
        ("Rent / deposit", f"{t['monthly_rent']} / {t['deposit']}"),
        ("Available", t["available_date"]), ("Website", cfg["site_url"]),
    ]
    for k, v in rows:
        print(f"      {k:<20} {v}")


SITES = {
    "ale": ("ALE Solutions", ale_solutions),
    "dvg": ("DVG / De La Ville Group", dvg),
    "shelterpoint": ("Shelter Point Solutions", shelterpoint),
    "oem": ("OEM Properties", oem),
    "alehousing": ("ALE Housing", ale_housing),
    "sedgwick": ("Sedgwick", sedgwick),
    "crs": ("CRS Temporary Housing", crs),
    "zillow": ("Zillow Rental Manager", zillow),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sites", nargs="*", help="site keys, or 'all'")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list or not args.sites:
        for k, (name, _) in SITES.items():
            print(f"  {k:<13} {name}")
        return
    keys = [k for k in SITES if k != "zillow"] if args.sites == ["all"] else args.sites
    bad = [k for k in keys if k not in SITES]
    if bad:
        sys.exit(f"Unknown site(s): {', '.join(bad)}")

    cfg = load()
    todo = [f"{s}.{k}" for s in ("owner", "property", "terms") for k, v in cfg[s].items()
            if isinstance(v, str) and v.strip() == "TODO"]
    if todo:
        print("Still TODO in property.yaml (those fields will be left blank):\n  " + "\n  ".join(todo))

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE), channel="chrome", headless=False, viewport=None, args=["--start-maximized"])
        for k in keys:
            name, fn = SITES[k]
            print(f"\n== {name}")
            page = ctx.new_page()
            try:
                fn(page, cfg)
            except Exception as e:
                print(f"   ! stopped early: {e}\n   Finish this one by hand in the open tab.")
            input("   Review the form in Chrome and click Submit yourself. Press Enter for the next site... ")
        input("\nAll done. Press Enter to close Chrome. ")
        ctx.close()


if __name__ == "__main__":
    main()
