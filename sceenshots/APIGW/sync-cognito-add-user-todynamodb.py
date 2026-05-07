import json
import boto3
import os
import logging
from datetime import datetime

# Initialize logger and DynamoDB resource
logger = logging.getLogger()
logger.setLevel(logging.INFO)
dynamodb = boto3.resource('dynamodb')
table_name = os.getenv('DYNAMODB_TABLE', 'onlineStore')
table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    """
    Cognito Post Confirmation Trigger: 
    Writes a new user to DynamoDB after they confirm their account.
    """
    logger.info(f"Received event: {json.dumps(event)}")

    # Extract user attributes from the Cognito event
    user_attributes = event['request']['userAttributes']
    user_id = user_attributes.get('sub')
    email = user_attributes.get('email')
    name = user_attributes.get('name', 'New User')

    if not user_id or not email:
        logger.error("Missing required user attributes (sub or email)")
        return event

    # Format keys to match your Flask app's patterns
    user_pk = f"USER#{user_id}"
    user_sk = datetime.utcnow().isoformat() + 'Z'
    gsi1pk = f"EMAIL#{email}"

    # Prepare the item for DynamoDB
    item = {
        'PK': user_pk,
        'SK': user_sk,
        'GSI1PK': gsi1pk,
        'GSI1SK': user_pk,
        'entityType': 'User',
        'email': email,
        'name': name,
        'email_verified': user_attributes.get('email_verified', 'false'),
        'createdAt': user_sk
    }

    try:
        # Write to DynamoDB
        table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(PK)'
        )
        logger.info(f"Successfully synced user {user_pk} to DynamoDB.")
    except Exception as e:
        logger.error(f"Error writing to DynamoDB: {str(e)}")
        # We don't raise the error to avoid blocking the user's login 
        # unless you want the login to fail if the DB write fails.

    # IMPORTANT: You must return the original event to Cognito
    return event