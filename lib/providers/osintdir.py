"""osintdir tier: curated master directory of OSINT tools, datasets and tradecraft references."""
RESOURCES = (
    ("bellingcat online investigation toolkit", "Bellingcat's Online Investigation Toolkit", "https://bellingcat.gitbook.io/toolkit", "tools, verification, geolocation"),
    ("osint framework", "OSINT Framework", "https://osintframework.com/", "directory of osint tools by category"),
    ("inteltechniques search tools", "IntelTechniques Search Tools", "https://inteltechniques.com/tools/", "email, username, domain search tools"),
    ("have i been pwned", "Have I Been Pwned", "https://haveibeenpwned.com/", "breach lookup by email"),
    ("dehashed", "DeHashed", "https://www.dehashed.com/", "breach search engine"),
    ("shodan", "Shodan", "https://www.shodan.io/", "internet-connected device search"),
    ("censys", "Censys Search", "https://search.censys.io/", "host & certificate search"),
    ("zoomeye", "ZoomEye", "https://www.zoomeye.hk/", "cyberspace search engine"),
    ("hunter.io", "Hunter", "https://hunter.io/", "email addresses by domain"),
    ("epieos", "Epieos", "https://epieos.com/", "email & phone to google account footprint"),
    ("emailrep", "EmailRep", "https://emailrep.io/", "email reputation"),
    ("namechk", "Namechk", "https://namechk.com/", "username availability across sites"),
    ("whatsmyname", "WhatsMyName", "https://whatsmyname.app/", "username enumeration across sites"),
    ("sherlock github", "Sherlock (GitHub)", "https://github.com/sherlock-project/sherlock", "username hunt across social networks"),
    ("maltego", "Maltego", "https://www.maltego.com/", "link analysis & entity graphing"),
    ("spiderfoot", "SpiderFoot", "https://github.com/smicallef/spiderfoot", "automated osint scanner (open source)"),
    ("theharvester", "theHarvester", "https://github.com/laramies/theHarvester", "emails, subdomains, hosts from public sources"),
    ("recon-ng", "Recon-ng", "https://github.com/lanmaster53/recon-ng", "web reconnaissance framework"),
    ("nuclei github", "Nuclei", "https://github.com/projectdiscovery/nuclei", "vulnerability scanner with template library"),
    ("urlscan io", "urlscan.io", "https://urlscan.io/", "page & infrastructure scan archive"),
    ("wayback machine", "Wayback Machine", "https://web.archive.org/", "archived web history"),
    ("archive today", "archive.today", "https://archive.ph/", "page snapshots"),
    ("wikileaks", "WikiLeaks", "https://wikileaks.org/", "leaked document archive"),
    ("dossier center dossie", "Dossier Center", "https://dossier.center/", "investigative archive"),
    ("occrp aleph", "OCCRP Aleph", "https://aleph.occrp.org/", "cross-border leak & registry search"),
    ("open corporates", "OpenCorporates", "https://opencorporates.com/", "company registry search worldwide"),
    ("sec edgar", "SEC EDGAR", "https://www.sec.gov/edgar/search/", "US company filings"),
    ("panamapapers icij", "ICIJ Offshore Leaks", "https://offshoreleaks.icij.org/", "offshore entities database"),
    ("flight radar", "Flightradar24", "https://www.flightradar24.com/", "live aircraft tracking"),
    ("marine traffic", "MarineTraffic", "https://www.marinetraffic.com/", "live vessel tracking"),
    ("sunCalc", "SunCalc", "https://www.suncalc.org/", "shadow-angle geolocation helper"),
    ("peakvisor", "PeakVisor", "https://peakvisor.com/", "mountain identification for photo geo-location"),
    ("yandex images", "Yandex Images", "https://yandex.com/images/", "reverse image search (strong for faces/places)"),
    ("bing visual search", "Bing Visual Search", "https://www.bing.com/visualsearch", "reverse image search"),
    ("tinEye", "TinEye", "https://tineye.com/", "reverse image search with sort by date"),
    ("imago images", "Imago", "https://www.imago-images.de/", "press photo search"),
    ("pimeye", "PimEyes", "https://pimeyes.com/", "face search (public web)"),
    ("hunchly", "Hunchly", "https://www.hunchly.com/", "investigation capture & documentation"),
    ("malwarebazaar", "MalwareBazaar", "https://bazaar.abuse.ch/", "malware sample database"),
    ("virustotal", "VirusTotal", "https://www.virustotal.com/", "file & url analysis"),
    ("dnstwist github", "dnstwist", "https://github.com/elceef/dnstwist", "domain typo-squatting detection"),
    ("view dns", "ViewDNS.info", "https://viewdns.info/", "dns record toolbox"),
    ("bgp he", "Hurricane Electric BGP", "https://bgp.he.net/", "asn & ip intelligence"),
    ("wiener si search", "WIENER Library", "https://www.wienerlibrary.co.uk/", "holocaust-era records"),
    ("prisoners of Google dorks", "Google Dorks (GHDB)", "https://www.exploit-db.com/google-hacking-database", "advanced search operators"),
)


def search(query: str, limit: int = 20) -> dict:
    words = [w for w in query.lower().split() if len(w) > 2] or []
    results = []
    for key, title, url, note in RESOURCES:
        hay = f"{key} {title.lower()} {note.lower()}"
        score = sum(1 for w in words if w in hay)
        if words and not score:
            continue
        results.append({"title": title, "author": note, "url": url, "snippet": note, "tier": "osintdir", "_score": score})
    results.sort(key=lambda r: r.pop("_score"), reverse=True)
    return {"results": results[:limit], "note": "curated OSINT master directory (tools, databases, tradecraft)"}
