"""
FII/DII (Foreign and Domestic Institutional Investor) data fetcher
"""
import requests
import csv
import io
from datetime import date, timedelta
from typing import Optional, Dict
import logging

LOG = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.nseindia.com/",
}


def get_fii_dii_data(target_date: Optional[date] = None) -> Dict:
    """Fetch FII/DII participant-wise trading data from NSE"""
    
    if target_date is None:
        # Default to yesterday (data has 1-day lag)
        target_date = date.today() - timedelta(days=1)
    
    vol_url = f'https://archives.nseindia.com/content/nsccl/fao_participant_vol_{target_date.strftime("%d%m%Y")}.csv'
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        r = session.get(vol_url, timeout=30)
        if r.status_code != 200:
            LOG.warning(f"FII/DII data not available for {target_date}")
            return None
        
        # Parse CSV
        lines = r.text.strip().split('\n')
        for i, line in enumerate(lines):
            if 'Client Type' in line:
                csv_data = '\n'.join(lines[i:])
                reader = csv.DictReader(io.StringIO(csv_data))
                
                result = {
                    'date': target_date.isoformat(),
                    'fii': None,
                    'dii': None
                }
                
                for row in reader:
                    row = {k.strip(): v.strip() for k, v in row.items()}
                    ct = row.get('Client Type', '')
                    
                    if ct == 'FII':
                        tl = int(row.get('Total Long Contracts', '0').replace(',', ''))
                        ts = int(row.get('Total Short Contracts', '0').replace(',', ''))
                        net = tl - ts
                        
                        result['fii'] = {
                            'long': tl,
                            'short': ts,
                            'net': net,
                            'sentiment': 'bullish' if net > 0 else 'bearish'
                        }
                    
                    elif ct == 'DII':
                        tl = int(row.get('Total Long Contracts', '0').replace(',', ''))
                        ts = int(row.get('Total Short Contracts', '0').replace(',', ''))
                        net = tl - ts
                        
                        result['dii'] = {
                            'long': tl,
                            'short': ts,
                            'net': net,
                            'sentiment': 'bullish' if net > 0 else 'bearish'
                        }
                
                return result
        
        return None
        
    except Exception as e:
        LOG.error(f"Error fetching FII/DII data: {e}")
        return None
