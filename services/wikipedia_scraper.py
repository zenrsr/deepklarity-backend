import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class WikipediaScraper:
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }
    
    def validate_wikipedia_url(self, url: str) -> bool:
        try:
            parsed_url = requests.utils.urlparse(url)
            return (
                parsed_url.netloc.endswith('wikipedia.org') and
                parsed_url.path.startswith('/wiki/') and
                len(parsed_url.path) > 6 
            )
        except Exception:
            return False
    
    def extract_article_title(self, url: str) -> str:
        try:
            parsed_url = requests.utils.urlparse(url)
            title = parsed_url.path.split('/wiki/')[-1]
            title = requests.utils.unquote(title).replace('_', ' ')
            return title.strip()
        except Exception as e:
            logger.error(f"Error extracting title from URL {url}: {e}")
            return "Unknown Article"
    
    def scrape_article(self, url: str) -> Dict[str, any]:
        """
        Scrape Wikipedia article and extract content
        
        Returns:
            Dict containing:
                - title: Article title
                - summary: Brief summary
                - content: Full article text
                - sections: List of section titles
                - key_entities: Dict with people, organizations, locations
        """
        try:
            if not self.validate_wikipedia_url(url):
                raise ValueError("Invalid Wikipedia URL")
            
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            self._remove_unwanted_elements(soup)
            
            title = self._extract_title(soup, url)
            
            summary = self._extract_summary(soup)
            
            content = self._extract_content(soup)
            
            sections = self._extract_sections(soup)
            
            key_entities = self._extract_key_entities(content, title)
            
            return {
                "title": title,
                "summary": summary,
                "content": content,
                "sections": sections,
                "key_entities": key_entities,
                "word_count": len(content.split()),
                "url": url
            }
            
        except requests.RequestException as e:
            logger.error(f"Network error scraping {url}: {e}")
            raise Exception(f"Failed to fetch Wikipedia article: {str(e)}")
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            raise Exception(f"Failed to scrape Wikipedia article: {str(e)}")
    
    def _remove_unwanted_elements(self, soup: BeautifulSoup) -> None:
        """Remove navigation, references, and other unwanted elements"""
        for toc in soup.find_all('div', {'id': 'toc'}):
            toc.decompose()
        
        for reflist in soup.find_all('div', {'class': 'reflist'}):
            reflist.decompose()
        
        for edit in soup.find_all('span', {'class': 'mw-editsection'}):
            edit.decompose()
        
        for infobox in soup.find_all('table', {'class': 'infobox'}):
            infobox.decompose()
        
        for navbox in soup.find_all('div', {'class': 'navbox'}):
            navbox.decompose()
        
        for citation in soup.find_all('sup', {'class': 'noprint'}):
            citation.decompose()
    
    def _extract_title(self, soup: BeautifulSoup, url: str) -> str:
        """Extract article title"""
        try:
            h1 = soup.find('h1', {'id': 'firstHeading'})
            if h1:
                return h1.get_text().strip()
            
            return self.extract_article_title(url)
        except Exception:
            return self.extract_article_title(url)
    
    def _extract_summary(self, soup: BeautifulSoup) -> str:
        """Extract the first paragraph as summary"""
        try:
            content_div = soup.find('div', {'id': 'mw-content-text'})
            if not content_div:
                return ""
            
            first_p = content_div.find('p')
            if first_p:
                summary = first_p.get_text().strip()
                summary = re.sub(r'\[\d+\]', '', summary) 
                summary = re.sub(r'\s+', ' ', summary) 
                return summary[:500] 
            
            return ""
        except Exception as e:
            logger.error(f"Error extracting summary: {e}")
            return ""
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main article content"""
        try:
            content_div = soup.find('div', {'id': 'mw-content-text'})
            if not content_div:
                return ""
            
            paragraphs = content_div.find_all('p')
            
            content_parts = []
            for p in paragraphs:
                text = p.get_text().strip()
                if text and len(text) > 50:
                    text = re.sub(r'\[\d+\]', '', text) 
                    text = re.sub(r'\s+', ' ', text)  
                    content_parts.append(text)
            
            return ' '.join(content_parts)
            
        except Exception as e:
            logger.error(f"Error extracting content: {e}")
            return ""
    
    def _extract_sections(self, soup: BeautifulSoup) -> List[str]:
        """Extract section headings"""
        try:
            sections = []
            

            headings = soup.find_all(['h2', 'h3'])
            
            for heading in headings:

                if heading.get('class') and any(
                    cls in ['mw-editsection', 'noprint'] for cls in heading.get('class', [])
                ):
                    continue
                
                text = heading.get_text().strip()
                if text and not text.lower().startswith('contents'):
                    sections.append(text)
            
            return sections[:10] 
            
        except Exception as e:
            logger.error(f"Error extracting sections: {e}")
            return []
    
    def _extract_key_entities(self, content: str, title: str) -> Dict[str, List[str]]:
        """Extract key entities (people, organizations, locations)"""
        try:


            
            key_entities = {
                "people": [],
                "organizations": [],
                "locations": []
            }
            


            people_patterns = [
                r'\b([A-Z][a-z]+ [A-Z][a-z]+)', 
                r'\b([A-Z]\. [A-Z][a-z]+)',       
            ]
            

            org_patterns = [
                r'\b([A-Z][a-z]+ (?:University|College|Institute|Corporation|Company|Group))',
                r'\b([A-Z]{2,}(?:\s[A-Z]{2,})*)', 
            ]
            

            location_patterns = [
                r'\b([A-Z][a-z]+ (?:City|Country|State|Province|Region))',
                r'\b([A-Z][a-z]+)',
            ]
            

            for pattern in people_patterns:
                matches = re.findall(pattern, content[:2000]) 
                key_entities["people"].extend(matches[:5])
            
            for pattern in org_patterns:
                matches = re.findall(pattern, content[:2000])
                key_entities["organizations"].extend(matches[:5])
            
            for pattern in location_patterns:
                matches = re.findall(pattern, content[:1000])
                key_entities["locations"].extend(matches[:3])
            

            for category in key_entities:
                key_entities[category] = list(set([
                    entity.strip() for entity in key_entities[category] 
                    if entity.strip() and len(entity.strip()) > 2
                ]))[:5] 
            
            return key_entities
            
        except Exception as e:
            logger.error(f"Error extracting key entities: {e}")
            return {"people": [], "organizations": [], "locations": []}


wikipedia_scraper = WikipediaScraper()