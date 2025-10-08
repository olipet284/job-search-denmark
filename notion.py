from notion_client import Client
import pandas as pd
from scrapers.config_loader import get_notion_config

notion_token, notion_database_id = get_notion_config()

notion = Client(auth=notion_token)

df = pd.read_csv('jobs.csv')
# make sure to start from the oldest (based on applied_date)
df = df.sort_values(by=['applied_date'], ascending=False)

first_date = None
allow_break = False
for index, row in df.iterrows():
    if first_date is None:
        first_date = row['applied_date']
    elif row['applied_date'] != first_date:
        allow_break = True
    
    if row['decision'] != 'apply' or row['applied_date'] == None or row['notion']:
        if allow_break:
            break
        continue
    
    notion.pages.create(
        parent={"database_id": notion_database_id},
        properties={
            'Name': {
                'title': [{
                    'text': {
                        'content': row['company'] + ' - ' + row['title'],
                    }
                }]
            },
            'Applied Date': {
                'date': {
                    'start': row['applied_date']
                }
            },
            'URL': {
                'url': row['url']
            },
            'Status': {
                'status': {
                    'name': 'Done'
                }
            }
        }
    )
    row['notion'] = True
df.to_csv('jobs.csv', index=False)