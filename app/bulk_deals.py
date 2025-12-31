"""
Fetch and parse bulk/block deals from NSE to identify FII/DII stock-specific trades
"""
import requests
import csv
import io
from datetime import date, timedelta
from typing import Optional, List, Dict
import logging
import re

LOG = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.nseindia.com/",
}

# Patterns to identify FII (Foreign Institutional Investors)
FII_PATTERNS = [
    r'morgan\s*stanley', r'goldman\s*sachs', r'hsbc', r'nomura', r'ubs', r'credit\s*suisse',
    r'deutsche', r'jp\s*morgan', r'citigroup', r'barclays', r'bnp\s*paribas',
    r'societe\s*generale', r'merrill\s*lynch', r'clsa', r'macquarie', r'fidelity',
    r'blackrock', r'vanguard', r'invesco', r'franklin\s*templeton', r'aberdeen',
    r'oppenheimer', r'emerging\s*markets', r'offshore', r'mauritius', r'singapore',
    r'foreign', r'fii', r'qfii'
]

# Patterns to identify DII (Domestic Institutional Investors)
DII_PATTERNS = [
    r'lic\b', r'life\s*insurance', r'general\s*insurance', r'mutual\s*fund',
    r'hdfc\s*(mf|mutual)', r'icici\s*(pru|mutual)', r'sbi\s*(mf|mutual)',
    r'birla\s*sun\s*life', r'reliance\s*mutual', r'kotak\s*mutual',
    r'axis\s*mutual', r'nippon\s*(india|mutual)', r'tata\s*mutual',
    r'mirae\s*asset', r'dsp', r'edelweiss', r'sundaram', r'idfc\s*mutual',
    r'provident\s*fund', r'pension\s*fund', r'psu\s*bank', r'insurance\s*co'
]


def classify_client(client_name: str) -> str:
    """Classify a client as FII, DII, or Other based on name patterns"""
    if not client_name:
        return 'Other'
    
    name_lower = client_name.lower()
    
    # Check FII patterns
    for pattern in FII_PATTERNS:
        if re.search(pattern, name_lower):
            return 'FII'
    
    # Check DII patterns
    for pattern in DII_PATTERNS:
        if re.search(pattern, name_lower):
            return 'DII'
    
    return 'Other'


def get_bulk_block_deals(target_date: Optional[date] = None) -> Dict:
    """Fetch bulk and block deals from NSE and classify by FII/DII"""
    
    if target_date is None:
        # Try yesterday first (data has 1-day lag)
        target_date = date.today() - timedelta(days=1)
    
    result = {
        'date': target_date.isoformat(),
        'bulk_deals': [],
        'block_deals': [],
        'fii_stocks': {},
        'dii_stocks': {},
        'summary': {
            'fii_buys': 0,
            'fii_sells': 0,
            'dii_buys': 0,
            'dii_sells': 0
        }
    }
    
    # Fetch bulk deals
    bulk_url = f'https://archives.nseindia.com/content/equities/bulk_{target_date.strftime("%d%m%Y")}.csv'
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        r = session.get(bulk_url, timeout=30)
        if r.status_code == 200 and len(r.content) > 500:
            deals = parse_deals_csv(r.content, 'bulk')
            result['bulk_deals'] = deals
            process_deals(deals, result)
    except Exception as e:
        LOG.warning(f"Could not fetch bulk deals for {target_date}: {e}")
    
    # Fetch block deals
    block_url = f'https://archives.nseindia.com/content/equities/block_{target_date.strftime("%d%m%Y")}.csv'
    try:
        r = session.get(block_url, timeout=30)
        if r.status_code == 200 and len(r.content) > 500:
            deals = parse_deals_csv(r.content, 'block')
            result['block_deals'] = deals
            process_deals(deals, result)
    except Exception as e:
        LOG.warning(f"Could not fetch block deals for {target_date}: {e}")
    
    # Aggregate by stock
    result['fii_stocks'] = sorted(
        [{'symbol': k, **v} for k, v in result['fii_stocks'].items()],
        key=lambda x: abs(x['net_quantity']),
        reverse=True
    )
    
    result['dii_stocks'] = sorted(
        [{'symbol': k, **v} for k, v in result['dii_stocks'].items()],
        key=lambda x: abs(x['net_quantity']),
        reverse=True
    )
    
    return result


def parse_deals_csv(content: bytes, deal_type: str) -> List[Dict]:
    """Parse bulk/block deals CSV"""
    deals = []
    
    try:
        txt = content.decode('utf-8', errors='replace')
        lines = txt.strip().split('\n')
        
        # Find CSV header
        header_idx = 0
        for i, line in enumerate(lines):
            if 'Symbol' in line or 'SYMBOL' in line:
                header_idx = i
                break
        
        csv_data = '\n'.join(lines[header_idx:])
        reader = csv.DictReader(io.StringIO(csv_data))
        
        for row in reader:
            # Normalize keys
            row = {k.strip(): v.strip() for k, v in row.items() if k}
            
            symbol = row.get('Symbol') or row.get('SYMBOL', '').strip()
            client = row.get('Client Name') or row.get('CLIENT NAME', '').strip()
            
            if not symbol or not client:
                continue
            
            buy_sell = (row.get('Buy/Sell') or row.get('BUY/SELL', '')).strip().upper()
            quantity_str = (row.get('Quantity') or row.get('QUANTITY', '')).strip()
            quantity = int(quantity_str.replace(',', '')) if quantity_str else 0
            
            classification = classify_client(client)
            
            if classification in ['FII', 'DII']:
                deals.append({
                    'type': deal_type,
                    'symbol': symbol,
                    'client': client,
                    'classification': classification,
                    'action': 'BUY' if 'BUY' in buy_sell else 'SELL',
                    'quantity': quantity
                })
        
    except Exception as e:
        LOG.error(f"Error parsing {deal_type} deals CSV: {e}")
    
    return deals


def process_deals(deals: List[Dict], result: Dict):
    """Process deals and aggregate by stock"""
    for deal in deals:
        classification = deal['classification']
        symbol = deal['symbol']
        action = deal['action']
        quantity = deal['quantity']
        
        # Update summary counts
        if classification == 'FII':
            if action == 'BUY':
                result['summary']['fii_buys'] += 1
            else:
                result['summary']['fii_sells'] += 1
            
            # Aggregate by stock
            if symbol not in result['fii_stocks']:
                result['fii_stocks'][symbol] = {
                    'buy_quantity': 0,
                    'sell_quantity': 0,
                    'net_quantity': 0,
                    'deals': []
                }
            
            if action == 'BUY':
                result['fii_stocks'][symbol]['buy_quantity'] += quantity
            else:
                result['fii_stocks'][symbol]['sell_quantity'] += quantity
            
            result['fii_stocks'][symbol]['net_quantity'] = (
                result['fii_stocks'][symbol]['buy_quantity'] - 
                result['fii_stocks'][symbol]['sell_quantity']
            )
            result['fii_stocks'][symbol]['deals'].append(deal)
        
        elif classification == 'DII':
            if action == 'BUY':
                result['summary']['dii_buys'] += 1
            else:
                result['summary']['dii_sells'] += 1
            
            # Aggregate by stock
            if symbol not in result['dii_stocks']:
                result['dii_stocks'][symbol] = {
                    'buy_quantity': 0,
                    'sell_quantity': 0,
                    'net_quantity': 0,
                    'deals': []
                }
            
            if action == 'BUY':
                result['dii_stocks'][symbol]['buy_quantity'] += quantity
            else:
                result['dii_stocks'][symbol]['sell_quantity'] += quantity
            
            result['dii_stocks'][symbol]['net_quantity'] = (
                result['dii_stocks'][symbol]['buy_quantity'] - 
                result['dii_stocks'][symbol]['sell_quantity']
            )
            result['dii_stocks'][symbol]['deals'].append(deal)
