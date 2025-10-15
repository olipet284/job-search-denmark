from notion_client import Client
import pandas as pd
from scrapers.config_loader import get_notion_config

notion_token, notion_database_id = get_notion_config()

notion = Client(auth=notion_token)

df = pd.read_csv('jobs.csv')
# make sure to start from the oldest (based on applied_date)
df = df.sort_values(by=['applied_date'], ascending=False)

message = ""
first_date = None
allow_break = False
for index, row in df.iterrows():
    if first_date is None:
        first_date = row['applied_date']
    elif row['applied_date'] != first_date:
        allow_break = True

    is_in_notion = row['notion'] if isinstance(row['notion'], bool) else False
    if row['decision'] != 'apply' or row['applied_date'] == None or is_in_notion:
        if allow_break:
            break
        continue

    message += f"Creating Notion page for {row['company']} - {row['title']} (applied {row['applied_date']})\n"
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

if message == "":
    message = "No new applications to add to Notion"
print(message)