import argparse
import boto3
from boto3.dynamodb.conditions import Attr
import functools
import operator


def get_table(profile_name: str, region_name: str, table_name: str):
    session = boto3.Session(profile_name=profile_name, region_name=region_name)
    return session.resource('dynamodb').Table(table_name)


def find_items(table, prefixes):
    # Build OR'd begins_with filter for the PK attribute
    conditions = [Attr('PK').begins_with(p) for p in prefixes]
    filter_expr = functools.reduce(operator.or_, conditions)

    items = []
    kwargs = {'FilterExpression': filter_expr}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get('Items', []))
        if 'LastEvaluatedKey' in resp:
            kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']
        else:
            break
    return items


def delete_items(table, items):
    if not items:
        return 0
    with table.batch_writer() as batch:
        for it in items:
            # assumes table primary key attributes are named PK and SK
            batch.delete_item(Key={'PK': it['PK'], 'SK': it['SK']})
    return len(items)


def main():
    parser = argparse.ArgumentParser(description='Find and optionally delete fake items from the onlineStore DynamoDB table.')
    parser.add_argument('--profile', default='diaa-gbg', help='AWS profile name')
    parser.add_argument('--region', default='us-east-2', help='AWS region')
    parser.add_argument('--table', default='onlineStore', help='DynamoDB table name')
    parser.add_argument('--execute', action='store_true', help='Actually delete found items. Without this flag the script only lists them (dry-run).')
    args = parser.parse_args()

    table = get_table(args.profile, args.region, args.table)

    prefixes = ['USER#', 'PROD#', 'ORDER#']
    print('Scanning for items with PK prefixes:', prefixes)
    items = find_items(table, prefixes)

    if not items:
        print('No matching items found.')
        return

    print(f'Found {len(items)} item(s). Sample keys:')
    for it in items[:10]:
        print('-', {'PK': it.get('PK'), 'SK': it.get('SK')})

    if not args.execute:
        print('\nDry-run mode. No items were deleted. Re-run with --execute to delete these items.')
        return

    count = delete_items(table, items)
    print(f'Deletion complete. Deleted {count} item(s).')


if __name__ == '__main__':
    main()
