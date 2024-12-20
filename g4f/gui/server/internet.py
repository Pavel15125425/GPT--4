from __future__ import annotations

from aiohttp import ClientSession
from bs4 import BeautifulSoup
import asyncio
import re
from duckduckgo_search import AsyncDDGS

from ... import debug

class SearchResultEntry:
    def __init__(self, title: str, url: str, snippet: str, text: str = None):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.text = text

class SearchResults:
    def __init__(self, results: list, used_words: int):
        self.results = results
        self.used_words = used_words

    def __str__(self):
        search = ""
        for idx, result in enumerate(self.results):
            if search:
                search += "\n\n\n"
            search += f"Title: {result.title}\n\n"
            if result.text:
                search += result.text
            else:
                search += result.snippet
            search += f"\n\nSource: [[{idx}]]({result.url})"
        return search

    def __len__(self) -> int:
        return len(self.results)

def clean_text(text: str, max_words: int = None) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    if max_words:
        words = text.split()
        text = ' '.join(words[:max_words])
    return text

async def search(query: str, n_results: int = 5, max_words: int = 2500, region: str = "wt-wt") -> SearchResults:
    try:
        async with AsyncDDGS() as ddgs:
            results = await ddgs.atext(
                keywords=query,
                max_results=n_results,
                backend='lite',
                region=region
            )
            
            if not results:
                results = await ddgs.atext(
                    keywords=query,
                    max_results=n_results,
                    backend='api',
                    region=region
                )
                
            if not results:
                debug.log("No search results found")
                return SearchResults([], 0)

            search_entries = []
            total_words = 0

            for result in results:
                url = result.get('link') or result.get('url') or result.get('href', '')
                
                entry = SearchResultEntry(
                    title=result.get('title', ''),
                    url=url,
                    snippet=result.get('body', '') or result.get('snippet', '') or result.get('text', '')
                )
                
                if entry.url:
                    try:
                        # Використовуємо метод request
                        response = ddgs.client.request('GET', url)
                        if response and response.content:
                            html_text = response.content.decode('utf-8', errors='ignore')
                            soup = BeautifulSoup(html_text, 'html.parser')
                            text_elements = soup.select('p, article, .content, .main-content')
                            content = ' '.join(elem.get_text() for elem in text_elements)
                            content = clean_text(content, max_words // n_results)
                            entry.text = content
                            total_words += len(content.split())
                    except Exception as e:
                        debug.log(f"Error fetching content from {url}: {e}")
                
                search_entries.append(entry)

            return SearchResults(search_entries, total_words)

    except Exception as e:
        debug.log(f"Search error: {str(e)}")
        try:
            async with AsyncDDGS() as ddgs:
                results = await ddgs.atext(
                    keywords=query,
                    max_results=n_results,
                    backend='api',
                    region=region
                )
                if results:
                    search_entries = [
                        SearchResultEntry(
                            title=r.get('title', ''),
                            url=r.get('link', ''),
                            snippet=r.get('body', ''),
                            text=None
                        ) for r in results
                    ]
                    return SearchResults(search_entries, 0)
        except Exception as e2:
            debug.log(f"Alternative search error: {str(e2)}")
        return SearchResults([], 0)

def get_search_message(prompt: str, n_results: int = 5, max_words: int = 2500, region: str = "wt-wt") -> str:
    try:
        debug.log(f"Web search: '{prompt.strip()[:50]}...'")
        
        search_results = asyncio.run(search(prompt, n_results, max_words, region))
        
        if not search_results or len(search_results) == 0:
            debug.log("No search results found")
            return prompt

        message = f"""
{search_results}

Instruction: Using the provided web search results, write a comprehensive reply to the user request.
Make sure to add the sources of cites using [[Number]](Url) notation after the reference.

User request:
{prompt}
"""
        debug.log(f"Search completed: {len(search_results)} results, {search_results.used_words} words")
        return message

    except Exception as e:
        debug.log(f"Error in get_search_message: {e}")
        return prompt
