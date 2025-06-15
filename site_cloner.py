#!/usr/bin/env python3
"""
Website Cloner - Downloads and recreates websites locally

This tool downloads the HTML, CSS, JS, and media files from a website and
recreates the folder structure locally, updating all links to point to the
local copies.
"""

import os
import sys
import argparse
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser
import threading
import queue
import re
import logging
import time
from typing import Set, Dict, List, Tuple, Optional, Any
import shutil
from pathlib import Path
import json
import gzip
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from tqdm import tqdm
import yaml
from concurrent.futures import ThreadPoolExecutor
import hashlib
from datetime import datetime
import mimetypes
import ssl
import certifi

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('WebsiteCloner')

# Global variables
visited_urls: Set[str] = set()
download_queue: queue.Queue = queue.Queue()
resource_count: Dict[str, int] = {
    'html': 0, 'css': 0, 'js': 0, 'img': 0, 'font': 0, 
    'video': 0, 'audio': 0, 'other': 0
}
lock = threading.Lock()
progress_bar = None

# Configuration defaults
DEFAULT_CONFIG = {
    'rate_limit': 1.0,  # requests per second
    'max_retries': 3,
    'timeout': 30,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'compress_files': True,
    'auth': {
        'username': None,
        'password': None
    },
    'exclude_patterns': [],
    'include_patterns': [],
    'max_file_size': 100 * 1024 * 1024,  # 100MB
    'verify_ssl': True
}


class ResourceHTMLParser(HTMLParser):
    """HTML Parser to extract resources from HTML files"""

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.resources = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        attr_dict = dict(attrs)
        
        # Extract resources based on HTML tag type
        if tag == 'link' and attr_dict.get('rel') == 'stylesheet' and attr_dict.get('href'):
            self.resources.append(('css', attr_dict['href']))
        elif tag == 'script' and attr_dict.get('src'):
            self.resources.append(('js', attr_dict['src']))
        elif tag == 'img' and attr_dict.get('src'):
            self.resources.append(('img', attr_dict['src']))
        elif tag == 'a' and attr_dict.get('href'):
            self.resources.append(('link', attr_dict['href']))
        elif tag == 'source' and attr_dict.get('src'):
            self.resources.append(('media', attr_dict['src']))
        elif tag == 'link' and attr_dict.get('rel') == 'icon' and attr_dict.get('href'):
            self.resources.append(('img', attr_dict['href']))
        elif tag == 'link' and attr_dict.get('rel') == 'canonical' and attr_dict.get('href'):
            self.resources.append(('link', attr_dict['href']))
        # Handle inline styles with background images
        elif 'style' in attr_dict and 'url(' in attr_dict['style']:
            # Extract URLs from inline styles using regex
            urls = re.findall(r'url\([\'"]?([^\'"())]+)[\'"]?\)', attr_dict['style'])
            for url in urls:
                self.resources.append(('img', url))


class CSSParser:
    """Parser to extract resources from CSS files"""
    
    @staticmethod
    def extract_resources(css_content: str, base_url: str) -> List[Tuple[str, str]]:
        resources = []
        
        # Extract URLs from CSS content using regex
        urls = re.findall(r'url\([\'"]?([^\'"())]+)[\'"]?\)', css_content)
        for url in urls:
            # Determine resource type based on extension
            ext = os.path.splitext(url)[1].lower()
            if ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'):
                resource_type = 'img'
            elif ext in ('.woff', '.woff2', '.ttf', '.eot', '.otf'):
                resource_type = 'font'
            else:
                resource_type = 'other'
            
            resources.append((resource_type, url))
            
        return resources


class URLProcessor:
    """Process and normalize URLs"""
    
    @staticmethod
    def normalize_url(url: str, base_url: str) -> str:
        """Convert relative URLs to absolute URLs"""
        return urllib.parse.urljoin(base_url, url)
    
    @staticmethod
    def is_same_domain(url: str, base_domain: str) -> bool:
        """Check if URL belongs to the same domain"""
        try:
            url_domain = urllib.parse.urlparse(url).netloc
            return url_domain == base_domain or not url_domain
        except Exception:
            return False
    
    @staticmethod
    def get_local_path(url: str, base_domain: str, output_dir: str) -> str:
        """Convert URL to local file path"""
        parsed_url = urllib.parse.urlparse(url)
        
        # Handle fragment identifiers and query parameters
        path = parsed_url.path
        if not path or path.endswith('/'):
            path = f"{path}index.html"
        
        # Ensure the domain directory exists for absolute URLs
        if parsed_url.netloc:
            domain_dir = os.path.join(output_dir, parsed_url.netloc)
            os.makedirs(domain_dir, exist_ok=True)
            return os.path.join(domain_dir, path.lstrip('/'))
        
        # For relative URLs, use the base domain
        domain_dir = os.path.join(output_dir, base_domain)
        return os.path.join(domain_dir, path.lstrip('/'))


class Downloader:
    """Handle downloading of resources"""
    
    def __init__(self, config: ConfigManager, output_dir: str):
        self.config = config
        self.output_dir = output_dir
        self.session_manager = SessionManager(config)
        self.skip_external = config.get('skip_external', True)
        self.compress_files = config.get('compress_files', True)
        self.max_file_size = config.get('max_file_size', 100 * 1024 * 1024)
    
    def should_download(self, url: str, resource_type: str) -> bool:
        """Check if resource should be downloaded based on configuration"""
        # Check exclude patterns
        for pattern in self.config.get('exclude_patterns', []):
            if re.search(pattern, url):
                return False
        
        # Check include patterns if specified
        include_patterns = self.config.get('include_patterns', [])
        if include_patterns:
            return any(re.search(pattern, url) for pattern in include_patterns)
        
        return True
    
    def download_resource(self, url: str, resource_type: str, base_domain: str) -> Optional[str]:
        """Download a resource and save it to the appropriate location"""
        if url in visited_urls or not self.should_download(url, resource_type):
            return None
        
        with lock:
            visited_urls.add(url)
        
        try:
            # Skip external domains if configured
            if self.skip_external and not URLProcessor.is_same_domain(url, base_domain):
                logger.info(f"Skipping external resource: {url}")
                return None
            
            # Normalize URL
            absolute_url = URLProcessor.normalize_url(url, f"https://{base_domain}")
            
            # Get local path for the resource
            local_path = URLProcessor.get_local_path(absolute_url, base_domain, self.output_dir)
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Download the resource with progress bar
            response = self.session_manager.get(absolute_url, stream=True)
            
            # Check file size
            content_length = int(response.headers.get('content-length', 0))
            if content_length > self.max_file_size:
                logger.warning(f"Skipping large file ({content_length} bytes): {url}")
                return None
            
            # Download with progress bar
            with open(local_path, 'wb') as out_file:
                with tqdm(
                    total=content_length,
                    unit='B',
                    unit_scale=True,
                    desc=f"Downloading {resource_type}",
                    leave=False
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            out_file.write(chunk)
                            pbar.update(len(chunk))
            
            # Compress file if enabled
            if self.compress_files and self._should_compress(local_path):
                self._compress_file(local_path)
            
            # Update resource count
            with lock:
                if resource_type in resource_count:
                    resource_count[resource_type] += 1
                else:
                    resource_count['other'] += 1
            
            logger.info(f"Downloaded {resource_type}: {url} -> {local_path}")
            return local_path
        
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return None
    
    def _should_compress(self, file_path: str) -> bool:
        """Check if file should be compressed based on type"""
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            return False
        
        compressible_types = {
            'text/html', 'text/css', 'text/javascript', 'application/javascript',
            'text/plain', 'application/json', 'application/xml'
        }
        return mime_type in compressible_types
    
    def _compress_file(self, file_path: str):
        """Compress a file using gzip"""
        try:
            with open(file_path, 'rb') as f_in:
                with gzip.open(f"{file_path}.gz", 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.remove(file_path)  # Remove original file
            os.rename(f"{file_path}.gz", file_path)  # Rename compressed file
        except Exception as e:
            logger.error(f"Failed to compress file {file_path}: {e}")


class WebsiteCloner:
    """Main class for website cloning"""
    
    def __init__(self, url: str, depth: int, threads: int, config_path: Optional[str] = None, output_dir: str = "cloned_site"):
        self.url = url
        self.depth = depth
        self.threads = threads
        self.output_dir = output_dir
        
        # Parse base domain
        self.base_domain = urllib.parse.urlparse(url).netloc
        
        # Initialize configuration
        self.config = ConfigManager(config_path)
        
        # Initialize downloader
        self.downloader = Downloader(self.config, output_dir)
        
        # Thread pool
        self.workers = []
        
        # Sitemap data
        self.sitemap = {
            'urls': [],
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'stats': resource_count.copy()
        }
    
    def start(self):
        """Start the cloning process"""
        logger.info(f"Starting website cloning process for {self.url}")
        logger.info(f"Base domain: {self.base_domain}")
        logger.info(f"Recursion depth: {self.depth}")
        logger.info(f"Thread count: {self.threads}")
        logger.info(f"Output directory: {self.output_dir}")
        
        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Add initial URL to queue
        download_queue.put((self.url, 'html', 0))
        
        # Start worker threads
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = []
            for i in range(self.threads):
                futures.append(executor.submit(self.worker, i))
            
            # Wait for all tasks to complete
            for future in futures:
                future.result()
        
        # Generate sitemap
        self.generate_sitemap()
        
        # Log summary
        logger.info("Website cloning complete!")
        logger.info(f"Downloaded resources:")
        for resource_type, count in resource_count.items():
            logger.info(f"  {resource_type}: {count}")
    
    def worker(self, worker_id: int):
        """Worker thread to process download queue"""
        logger.debug(f"Worker {worker_id} started")
        
        while True:
            try:
                # Get next URL from queue
                url, resource_type, current_depth = download_queue.get()
                
                # Process URL
                self.process_url(url, resource_type, current_depth)
                
                # Mark task as done
                download_queue.task_done()
                
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} encountered an error: {e}")
                download_queue.task_done()
    
    def process_url(self, url: str, resource_type: str, current_depth: int):
        """Process a URL and its resources"""
        try:
            # Download the resource
            local_path = self.downloader.download_resource(url, resource_type, self.base_domain)
            if not local_path:
                return
            
            # Add to sitemap
            self.sitemap['urls'].append({
                'url': url,
                'local_path': local_path,
                'type': resource_type,
                'depth': current_depth,
                'timestamp': datetime.now().isoformat()
            })
            
            # Process based on resource type
            if resource_type == 'html' and current_depth < self.depth:
                self.process_html(url, local_path, current_depth)
            elif resource_type == 'css':
                self.process_css(url, local_path)
        
        except Exception as e:
            logger.error(f"Failed to process {url}: {e}")
    
    def process_html(self, url: str, local_path: str, current_depth: int):
        """Process HTML file and extract resources"""
        try:
            with open(local_path, 'r', encoding='utf-8', errors='replace') as f:
                html_content = f.read()
            
            # Parse HTML
            parser = ResourceHTMLParser(url)
            parser.feed(html_content)
            
            # Process extracted resources
            for resource_type, resource_url in parser.resources:
                absolute_url = URLProcessor.normalize_url(resource_url, url)
                
                # Add to download queue
                if resource_type == 'link' and current_depth < self.depth:
                    download_queue.put((absolute_url, 'html', current_depth + 1))
                else:
                    download_queue.put((absolute_url, resource_type, current_depth))
            
            # Update HTML content with local paths
            updated_html = self.update_html_links(html_content, url)
            
            # Save updated HTML
            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(updated_html)
        
        except Exception as e:
            logger.error(f"Failed to process HTML {url}: {e}")
    
    def process_css(self, url: str, local_path: str):
        """Process CSS file and extract resources"""
        try:
            with open(local_path, 'r', encoding='utf-8', errors='replace') as f:
                css_content = f.read()
            
            # Extract resources from CSS
            resources = CSSParser.extract_resources(css_content, url)
            
            # Process extracted resources
            for resource_type, resource_url in resources:
                absolute_url = URLProcessor.normalize_url(resource_url, url)
                download_queue.put((absolute_url, resource_type, 0))
            
            # Update CSS content with local paths
            updated_css = self.update_css_links(css_content, url)
            
            # Save updated CSS
            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(updated_css)
        
        except Exception as e:
            logger.error(f"Failed to process CSS {url}: {e}")
    
    def update_html_links(self, html_content: str, base_url: str) -> str:
        """Update links in HTML to point to local files"""
        # Update href attributes
        html_content = re.sub(
            r'href=[\'"]([^\'"]+)[\'"]',
            lambda m: f'href="{self.get_local_reference(m.group(1), base_url)}"',
            html_content
        )
        
        # Update src attributes
        html_content = re.sub(
            r'src=[\'"]([^\'"]+)[\'"]',
            lambda m: f'src="{self.get_local_reference(m.group(1), base_url)}"',
            html_content
        )
        
        # Update style attributes with url()
        html_content = re.sub(
            r'style=[\'"][^\'"]*url\([\'"]?([^\'"()]+)[\'"]?\)[^\'"]*[\'"]',
            lambda m: f'style="background-image: url({self.get_local_reference(m.group(1), base_url)})"',
            html_content
        )
        
        return html_content
    
    def update_css_links(self, css_content: str, base_url: str) -> str:
        """Update links in CSS to point to local files"""
        return re.sub(
            r'url\([\'"]?([^\'"()]+)[\'"]?\)',
            lambda m: f'url({self.get_local_reference(m.group(1), base_url)})',
            css_content
        )
    
    def get_local_reference(self, url: str, base_url: str) -> str:
        """Convert a URL to a local reference"""
        # Skip data URLs and anchors
        if url.startswith('data:') or url.startswith('#'):
            return url
        
        # Normalize URL
        absolute_url = URLProcessor.normalize_url(url, base_url)
        parsed_url = urllib.parse.urlparse(absolute_url)
        
        # Handle external domains
        if self.skip_external and parsed_url.netloc and parsed_url.netloc != self.base_domain:
            return url
        
        # Get path relative to base domain directory
        if parsed_url.netloc == self.base_domain:
            return f"/{parsed_url.path.lstrip('/')}"
        elif not parsed_url.netloc:
            return url
        else:
            return f"/{parsed_url.netloc}/{parsed_url.path.lstrip('/')}"
    
    def generate_sitemap(self):
        """Generate sitemap and statistics"""
        self.sitemap['end_time'] = datetime.now().isoformat()
        self.sitemap['stats'] = resource_count.copy()
        
        # Save sitemap as JSON
        sitemap_path = os.path.join(self.output_dir, 'sitemap.json')
        with open(sitemap_path, 'w') as f:
            json.dump(self.sitemap, f, indent=2)
        
        # Generate HTML sitemap
        html_sitemap = self._generate_html_sitemap()
        html_sitemap_path = os.path.join(self.output_dir, 'sitemap.html')
        with open(html_sitemap_path, 'w') as f:
            f.write(html_sitemap)
        
        logger.info(f"Sitemap generated: {sitemap_path}")
        logger.info(f"HTML sitemap generated: {html_sitemap_path}")
    
    def _generate_html_sitemap(self) -> str:
        """Generate HTML sitemap"""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sitemap - {self.base_domain}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .stats {{ margin-bottom: 20px; }}
        .url-list {{ list-style: none; padding: 0; }}
        .url-item {{ margin: 10px 0; padding: 10px; border: 1px solid #ddd; }}
        .url-item:hover {{ background-color: #f5f5f5; }}
        .type-badge {{ 
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 12px;
            color: white;
            margin-right: 10px;
        }}
        .type-html {{ background-color: #007bff; }}
        .type-css {{ background-color: #28a745; }}
        .type-js {{ background-color: #ffc107; }}
        .type-img {{ background-color: #dc3545; }}
        .type-other {{ background-color: #6c757d; }}
    </style>
</head>
<body>
    <h1>Sitemap for {self.base_domain}</h1>
    <div class="stats">
        <h2>Statistics</h2>
        <p>Start time: {self.sitemap['start_time']}</p>
        <p>End time: {self.sitemap['end_time']}</p>
        <h3>Downloaded Resources:</h3>
        <ul>
"""
        
        for resource_type, count in self.sitemap['stats'].items():
            html += f"            <li>{resource_type}: {count}</li>\n"
        
        html += """        </ul>
    </div>
    <h2>URLs</h2>
    <ul class="url-list">
"""
        
        for url_data in self.sitemap['urls']:
            html += f"""        <li class="url-item">
            <span class="type-badge type-{url_data['type']}">{url_data['type']}</span>
            <a href="{url_data['local_path']}" target="_blank">{url_data['url']}</a>
            <small>(Depth: {url_data['depth']})</small>
        </li>
"""
        
        html += """    </ul>
</body>
</html>"""
        
        return html


class ConfigManager:
    """Handles loading and managing configuration"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = DEFAULT_CONFIG.copy()
        if config_path and os.path.exists(config_path):
            self.load_config(config_path)
    
    def load_config(self, config_path: str):
        """Load configuration from YAML or JSON file"""
        try:
            with open(config_path, 'r') as f:
                if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                    config = yaml.safe_load(f)
                elif config_path.endswith('.json'):
                    config = json.load(f)
                else:
                    raise ValueError("Configuration file must be YAML or JSON")
                
                self.config.update(config)
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)


class SessionManager:
    """Manages HTTP sessions with retry logic and rate limiting"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.session = requests.Session()
        self.last_request_time = 0
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=config.get('max_retries', 3),
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504]
        )
        
        # Configure adapter with retry strategy
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            'User-Agent': config.get('user_agent'),
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate'
        })
        
        # Configure authentication if provided
        auth = config.get('auth')
        if auth and auth.get('username') and auth.get('password'):
            self.session.auth = (auth['username'], auth['password'])
    
    def get(self, url: str, stream: bool = False) -> requests.Response:
        """Make a GET request with rate limiting"""
        # Implement rate limiting
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.config.get('rate_limit', 1.0):
            time.sleep(self.config.get('rate_limit', 1.0) - time_since_last_request)
        
        self.last_request_time = time.time()
        
        # Make request with configured timeout
        response = self.session.get(
            url,
            stream=stream,
            timeout=self.config.get('timeout', 30),
            verify=self.config.get('verify_ssl', True)
        )
        response.raise_for_status()
        return response


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Website Cloner')
    parser.add_argument('url', help='URL of the website to clone')
    parser.add_argument('-d', '--depth', type=int, default=2,
                      help='Maximum recursion depth (default: 2)')
    parser.add_argument('-t', '--threads', type=int, default=4,
                      help='Number of download threads (default: 4)')
    parser.add_argument('-o', '--output', default='cloned_site',
                      help='Output directory (default: cloned_site)')
    parser.add_argument('-c', '--config',
                      help='Path to configuration file (YAML or JSON)')
    parser.add_argument('--no-compress', action='store_true',
                      help='Disable file compression')
    parser.add_argument('--no-verify-ssl', action='store_true',
                      help='Disable SSL verification')
    parser.add_argument('--rate-limit', type=float, default=1.0,
                      help='Rate limit in requests per second (default: 1.0)')
    parser.add_argument('--max-file-size', type=int, default=100 * 1024 * 1024,
                      help='Maximum file size in bytes (default: 100MB)')
    parser.add_argument('--auth-username',
                      help='Username for HTTP authentication')
    parser.add_argument('--auth-password',
                      help='Password for HTTP authentication')
    parser.add_argument('--exclude', action='append',
                      help='Regex pattern to exclude URLs')
    parser.add_argument('--include', action='append',
                      help='Regex pattern to include URLs')
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)
    
    # Create configuration
    config = {
        'rate_limit': args.rate_limit,
        'compress_files': not args.no_compress,
        'verify_ssl': not args.no_verify_ssl,
        'max_file_size': args.max_file_size,
        'exclude_patterns': args.exclude or [],
        'include_patterns': args.include or []
    }
    
    if args.auth_username and args.auth_password:
        config['auth'] = {
            'username': args.auth_username,
            'password': args.auth_password
        }
    
    # Save configuration
    config_path = os.path.join(output_dir, 'config.json')
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    # Start cloning process
    cloner = WebsiteCloner(args.url, args.depth, args.threads, config_path, output_dir)
    try:
        start_time = time.time()
        cloner.start()
        end_time = time.time()
        
        logger.info(f"Cloning completed in {end_time - start_time:.2f} seconds")
        logger.info(f"Configuration saved to: {config_path}")
        
    except KeyboardInterrupt:
        logger.info("Cloning interrupted by user")
    except Exception as e:
        logger.error(f"Cloning failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()