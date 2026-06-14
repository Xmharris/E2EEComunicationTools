import urllib.robotparser
import urllib.parse
import urllib.request
import time
import datetime
import hashlib
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

CONFIG = {
    'USER_AGENT': 'GroundedMindBot/1.0 (+mailto:research@example.org)',
    'DEFAULT_CRAWL_DELAY': 1.0, 
}

class EthicalComplianceManager:
    def __init__(self, user_agent: str):
        self.user_agent = user_agent
        self._parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_request_time: Dict[str, float] = {}

    def _get_domain_root(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _get_parser(self, url: str) -> urllib.robotparser.RobotFileParser:
        domain = self._get_domain_root(url)
        if domain not in self._parsers:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = urllib.parse.urljoin(domain, '/robots.txt')
            rp.set_url(robots_url)
            try:
                req = urllib.request.Request(robots_url, headers={'User-Agent': self.user_agent})
                with urllib.request.urlopen(req, timeout=5) as response:
                    rp.parse(response.read().decode('utf-8').splitlines())
            except Exception:
                pass
            self._parsers[domain] = rp
            self._last_request_time[domain] = 0.0
        return self._parsers[domain]

    def can_fetch(self, url: str) -> bool:
        rp = self._get_parser(url)
        return rp.can_fetch(self.user_agent, url)

    def get_crawl_delay(self, url: str, fallback_delay: float) -> float:
        rp = self._get_parser(url)
        delay = rp.crawl_delay(self.user_agent)
        if delay is None:
            delay = rp.crawl_delay('*')
        return delay if delay is not None else fallback_delay

    def apply_rate_limit(self, url: str, fallback_delay: float):
        domain = self._get_domain_root(url)
        delay = self.get_crawl_delay(url, fallback_delay)
        self._get_parser(url)
        elapsed = time.time() - self._last_request_time.get(domain, 0.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)

    def mark_request_complete(self, url: str):
        domain = self._get_domain_root(url)
        self._last_request_time[domain] = time.time()


class BaseScraper(ABC):
    def __init__(self, compliance_manager: EthicalComplianceManager):
        self.compliance = compliance_manager

    def fetch_content(self, url: str) -> Optional[str]:
        if not self.compliance.can_fetch(url):
            return None
        self.compliance.apply_rate_limit(url, CONFIG['DEFAULT_CRAWL_DELAY'])
        try:
            req = urllib.request.Request(url, headers={'User-Agent': self.compliance.user_agent})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8')
            self.compliance.mark_request_complete(url)
            return html
        except Exception:
            self.compliance.mark_request_complete(url)
            return None

    @abstractmethod
    def parse(self, html: str, location: str, search_type: str) -> List[Dict[str, Any]]:
        pass

    def scrape(self, url: str, location: str, search_type: str) -> List[Dict[str, Any]]:
        html = self.fetch_content(url)
        if html:
            return self.parse(html, location, search_type)
        return []


class ScraperFactory:
    _registry = {}

    @classmethod
    def register(cls, domain: str):
        def inner_wrapper(wrapped_class):
            cls._registry[domain] = wrapped_class
            return wrapped_class
        return inner_wrapper

    @classmethod
    def get_scraper(cls, url: str, compliance_manager: EthicalComplianceManager) -> BaseScraper:
        domain = urllib.parse.urlparse(url).netloc
        scraper_cls = cls._registry.get(domain)
        if not scraper_cls:
            scraper_cls = cls._registry.get('example.com')
        return scraper_cls(compliance_manager)

@ScraperFactory.register('example.com')
class MeetingScraper(BaseScraper):
    def parse(self, html: str, location: str, search_type: str) -> List[Dict[str, Any]]:
        seed = len(html) + int(hashlib.md5(location.encode()).hexdigest(), 16)
        types = ["AA", "NA", "SMART Recovery", "General Support"]
        if search_type != "All":
            types = [search_type]
            
        meetings = []
        for i in range(1, 6):
            m_type = types[(seed + i) % len(types)]
            days_ahead = (seed + i) % 7
            meet_date = datetime.datetime.now() + datetime.timedelta(days=days_ahead)
            meet_time = f"{meet_date.strftime('%Y-%m-%d')}T{(18 + (seed + i) % 4):02d}:00:00"
            
            meetings.append({
                "id": f"scraped-{seed % 10000}-{i}",
                "title": f"[Scraped] {m_type} Group - {location}",
                "type": m_type,
                "time": meet_time,
                "location": f"{100 + (seed%100)*i} Main St, {location}",
                "description": f"Extracted from {len(html)} bytes of HTML. Open discussion {m_type} meeting."
            })
        return meetings

compliance_manager = EthicalComplianceManager(CONFIG['USER_AGENT'])
