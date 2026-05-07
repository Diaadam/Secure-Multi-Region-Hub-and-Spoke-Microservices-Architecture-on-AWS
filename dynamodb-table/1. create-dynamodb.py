import sys 
import argparse
import time
import json
import socket
from urllib.parse import urlparse
try: 
    import boto3
    from botocore.exceptions import (
            ProfileNotFound,
            NoRegionError,
            NoCredentialsError,
            PartialCredentialsError,
            EndpointConnectionError,
            WaiterError,
            ConnectTimeoutError,
            ReadTimeoutError,
            UnknownServiceError,
            ClientError

    )
except ModuleNotFoundError :
    print("Please Install boto3 Module First and Retry")
    sys.exit(1)

def main():
    try:
#*******************************************parsing arguments******************************** 
        parser = argparse.ArgumentParser(description="Create an IAM User ")
        parser.add_argument('-p', '--profileName',required=True, help="AWS CLI Profile Name ")
        parser.add_argument('-r', '--region', required=False, help="AWS region override (e.g., us-east-1)")
        parser.add_argument('-t', '--tableName',required=True, help="Dynamodb table to create")
        parser.add_argument('-sk', '--sortKey',required=True, help="table range key")
        parser.add_argument('-pk', '--partitionKey',required=True, help="table Hash key")
        parser.add_argument('-attr', '--attributeDefinitions',required=True,
                             help="""a list of [{"AttributeName": "id", "AttributeType": "S"}] """)
        parser.add_argument('-lsi', '--localSecondaryIndexes', required=False,
                             help='optional JSON list for LocalSecondaryIndexes')
        parser.add_argument('-gsi', '--globalSecondaryIndexes', required=False,
                             help='optional JSON list for GlobalSecondaryIndexes')
        
        args = parser.parse_args()
        profileName=args.profileName
        region_name=args.region
        table_name=args.tableName
        sort_key=args.sortKey
        part_key=args.partitionKey
        local_secondary_indexes = None
        global_secondary_indexes = None

        try:
            attributeDefinitions = json.loads(args.attributeDefinitions)
        except json.JSONDecodeError:
            raise ValueError("attributeDefinitions must be valid JSON")

        if not isinstance(attributeDefinitions, list):
            raise ValueError("attributeDefinitions must be a JSON list")

        for attr in attributeDefinitions:
            if not isinstance(attr, dict):
                raise ValueError("Each attribute definition must be a JSON object")
            if "AttributeName" not in attr or "AttributeType" not in attr:
                raise ValueError("Each attribute definition must include AttributeName and AttributeType")

        if args.localSecondaryIndexes:
            try:
                local_secondary_indexes = json.loads(args.localSecondaryIndexes)
            except json.JSONDecodeError:
                raise ValueError("localSecondaryIndexes must be valid JSON")
            if not isinstance(local_secondary_indexes, list):
                raise ValueError("localSecondaryIndexes must be a JSON list")

        if args.globalSecondaryIndexes:
            try:
                global_secondary_indexes = json.loads(args.globalSecondaryIndexes)
            except json.JSONDecodeError:
                raise ValueError("globalSecondaryIndexes must be valid JSON")
            if not isinstance(global_secondary_indexes, list):
                raise ValueError("globalSecondaryIndexes must be a JSON list")
  #*******************************************session and the aws resource/client********************     
        session = boto3.Session(profile_name=profileName, region_name=region_name)
        dynamodb_resource = session.resource('dynamodb')
        resource_client = dynamodb_resource.meta.client

        resolved_region = session.region_name or resource_client.meta.region_name
        endpoint_url = resource_client.meta.endpoint_url
        credentials = session.get_credentials()

        print("Preflight check:")
        print(f"  Profile: {profileName}")
        print(f"  Region: {resolved_region}")
        print(f"  DynamoDB endpoint: {endpoint_url}")
        if credentials is None:
            print("  Credentials: NOT FOUND")
        else:
            print(f"  Credentials source: {getattr(credentials, 'method', 'unknown')}")

        endpoint_host = urlparse(endpoint_url).hostname
        if endpoint_host:
            try:
                socket.getaddrinfo(endpoint_host, 443)
                print(f"  DNS resolution: OK ({endpoint_host})")
            except OSError as e:
                print(f"  DNS resolution: FAILED ({endpoint_host}) -> {e}")
 #******************************Develop Python boto3 logic for your requirement**********************
        print(f"Creating the table...")
        try:
            create_table_args = {
                'TableName': table_name,
                'KeySchema': [
                    {
                        'AttributeName': part_key,
                        'KeyType': 'HASH'
                    },
                    {
                        'AttributeName': sort_key,
                        'KeyType': 'RANGE'
                    }
                ],
                'AttributeDefinitions': attributeDefinitions,
                'BillingMode': 'PAY_PER_REQUEST'
            }

            if local_secondary_indexes is not None:
                create_table_args['LocalSecondaryIndexes'] = local_secondary_indexes
            if global_secondary_indexes is not None:
                create_table_args['GlobalSecondaryIndexes'] = global_secondary_indexes

            table = dynamodb_resource.create_table(**create_table_args)
            table.wait_until_exists()
            print("table created")
            
#****************************************code errors ********************************************************            
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ResourceInUseException":
                print("Table already exists")
            else:
                raise
#*********************************************other errors***************************************************
    except ProfileNotFound:
        print("Error : AWS CLI profile not found. Please check the profile name.")    
        sys.exit(1)
    except NoRegionError:
        print("Error : AWS region not specified. Use --region or set it in your config.")
        sys.exit(1)
    except NoCredentialsError:
        print("Error : AWS credentials not found. Please configure them using 'aws configure'.")
        sys.exit(1)
    except PartialCredentialsError:
        print("Error : Incomplete credentials. Please provide both Access Key and Secret Key.")
        sys.exit(1)
    except EndpointConnectionError:
        print("Error : Could not connect to AWS endpoint. Check your internet or region name.")
        sys.exit(1)
    except ConnectTimeoutError:
        print("Error : Connection to AWS timed out while trying to establish connection.")
        sys.exit(1)
    except ReadTimeoutError:
        print("Error : Connected, but AWS service didn't respond in time.")
        sys.exit(1)
    except WaiterError as e:
        print(f"Error : Waiter error: {e}")
        sys.exit(1)
    except UnknownServiceError as e:
        print(f"Error : UnknownServiceError: {e}. The service name might be incorrect or unsupported in this region.")
        sys.exit(1)
    except AttributeError as e:
        print(f"Error : AttributeError : {e} ")
        sys.exit(1)
    except ValueError as e:
        print(f"Error : {e}")
        sys.exit(1)
    except ClientError as e:
        errorCode=e.response['Error']['Code']
        errorMessage=e.response['Error']['Message']
        print(f"Error : AWS service Error -> code : {errorCode} and Message: {errorMessage}")
        sys.exit(1)
    except Exception as e:
        print("Error : Unexpected Error:", str(e))
        sys.exit(1)
    return None 

if __name__ == "__main__":
    main()