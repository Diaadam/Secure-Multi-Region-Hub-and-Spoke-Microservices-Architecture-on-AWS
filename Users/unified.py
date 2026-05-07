try: 
    from flask import Flask, request, render_template
    import json
    import boto3 
    import logging
    import os
    # import html
    # import re
    import sys
    from boto3.dynamodb.conditions import Key
    from decimal import Decimal
    from aws_xray_sdk.core import xray_recorder
    from aws_xray_sdk.ext.flask.middleware import XRayMiddleware
    from aws_xray_sdk.core import patch_all
    from botocore.exceptions import (
            ProfileNotFound,
            NoRegionError,
            NoCredentialsError,
            PartialCredentialsError,
            EndpointConnectionError,
            ConnectTimeoutError,
            ReadTimeoutError,
            UnknownServiceError,
            ClientError

    )

except ModuleNotFoundError as e:
    print(f"Error: Required module not found - {e}")
    logging.error(f"Error: Required module not found - {e}")
    sys.exit(1)
 #######################################################################   

logger = logging.getLogger('users_api')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s'
)

app = Flask(__name__)
try:
        session= boto3.Session()
        dynamodb_resource = session.resource('dynamodb')
        table_name = os.getenv('DYNAMODB_TABLE', 'onlineStore')
        table = dynamodb_resource.Table(table_name)
        cognito_client = session.client('cognito-idp')
        cognito_user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        cognito_setup_error = None
        if cognito_user_pool_id:
            logger.info('Cognito integration enabled user_pool_id=%s', cognito_user_pool_id)
        else:
            cognito_setup_error = 'COGNITO_USER_POOL_ID is not configured'
            logger.warning('Cognito integration disabled; set COGNITO_USER_POOL_ID to enable provisioning')

        credentials = session.get_credentials()

        if credentials is None:
            logger.info("  Credentials: NOT FOUND")
        else:
            logger.info(f"  Credentials source: {getattr(credentials, 'method', 'unknown')}")

except ProfileNotFound:
    logging.error("Error : AWS CLI profile not found. Please check the profile name.")
    sys.exit(1)
# except NoRegionError:
#     logging.error("Error : AWS region not specified. Use --region or set it in your config.")
#     sys.exit(1)
# aws will auto-detect region from env vars
except NoCredentialsError:
    logging.error("Error : AWS credentials not found. Please configure them using 'aws configure'.")
    sys.exit(1)
except PartialCredentialsError:
    logging.error("Error : Incomplete credentials. Please provide both Access Key and Secret Key.")
    sys.exit(1)
except EndpointConnectionError:
    logging.error("Error : Could not connect to AWS endpoint. Check your internet or region name.")
    sys.exit(1)
except ConnectTimeoutError:
    logging.error("Error : Connection to AWS timed out while trying to establish connection.")
    sys.exit(1)
except ReadTimeoutError:
    logging.error("Error : Connected, but AWS service didn't respond in time.")
    sys.exit(1)

except UnknownServiceError as e:
    logging.error(f"Error : UnknownServiceError: {e}. The service name might be incorrect or unsupported in this region.")
    sys.exit(1)

except ValueError as e:
    logging.error(f"Error : ValueError: {e}")
    sys.exit(1)

except Exception as e:
    logging.error(f"Error : Unexpected Error: {e}")
    sys.exit(1)
####################################################



# Configure X-Ray tracing (conditional for local development)
enable_xray = os.getenv('ENABLE_XRAY', 'false').lower() == 'true'
if enable_xray:
    logger.info("X-Ray tracing enabled")
    patch_all()
    xray_recorder.configure(service='Flask-API')
    XRayMiddleware(app, xray_recorder)
else:
    logger.info("X-Ray tracing disabled (set ENABLE_XRAY=true to enable)")

@app.route('/')
def health():
    logger.info('route=/ method=%s', request.method)
    return 'OK'



@app.route('/Users')
def get_all_users():
    logger.info('route=/Users method=%s', request.method)
    try:
        response = table.scan(Limit=100)  # Limit to 100 items for demo purposes
        body = response['Items']
        logger.info('route=/Users items_count=%s', len(body))
        return create_response(200, body)
    except ClientError as e:
        logger.exception('route=/Users aws_client_error')
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/Users unexpected_error')
        return create_response(500, {'message': str(e)})

@app.route('/Users/<email>')
def get_user_by_email(email):
    logger.info('route=/Users/<email> method=%s email=%s', request.method, email)
    try:
        # Try both raw email and EMAIL#-prefixed form for consistency
        email_keys = [ email] if email.startswith('EMAIL#') else [f'EMAIL#{email}', email ]
        body = None
        for email_key in email_keys:
            response = table.query(
                IndexName='GSI1',
                KeyConditionExpression=Key('GSI1PK').eq(email_key),
                Limit=1
            )
            items = response.get('Items', [])
            if items:
                body = items[0]
                break
        
        logger.info('route=/Users/<email> found=%s', body is not None)
        return create_response(200, body)
    except ClientError as e:
        logger.exception('route=/Users/<email> aws_client_error email=%s', email)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/Users/<email> unexpected_error email=%s', email)
        return create_response(500, {'message': str(e)})

@app.route('/getUserById/<id>')
def get_user_by_id(id):
    logger.info('route=/getUserById method=%s id=%s', request.method, id)
    try:
        # Query GSI1PK (secondary index) for the id
        response = table.query(
            IndexName='GSI1',
            KeyConditionExpression=Key('GSI1PK').eq(id),
            Limit=1
        )
        items = response.get('Items', [])
        body = items[0] if items else None
        logger.info('route=/getUserById found=%s id=%s', body is not None, id)
        return create_response(200, body)
    except ClientError as e:
        logger.exception('route=/getUserById aws_client_error id=%s', id)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/getUserById unexpected_error id=%s', id)
        return create_response(500, {'message': str(e)})


@app.route('/Users', methods=['POST'])
def create_user():
    from datetime import datetime

    payload = request.get_json(silent=True) or {}
    logger.info('route=/Users method=%s payload_keys=%s', request.method, list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__)
    if not isinstance(payload, dict) or not payload:
        return create_response(400, {'message': 'Request body must be a non-empty JSON object'})

    if not cognito_user_pool_id:
        return create_response(500, {'message': cognito_setup_error or 'Cognito user pool is not configured'})

    raw_id = payload.get('id')
    email = payload.get('email')

    if not raw_id:
        return create_response(400, {'message': 'id is required'})
    if not email:
        return create_response(400, {'message': 'email is required'})

    user_pk = raw_id if str(raw_id).startswith('USER#') else f'USER#{raw_id}'
    user_sk = payload.get('SK') or (datetime.utcnow().isoformat() + 'Z')

    gsi1pk = payload.get('GSI1PK')
    if not gsi1pk:
        gsi1pk = email if str(email).startswith('EMAIL#') else f'EMAIL#{email}'

    item = {
        'PK': user_pk,
        'SK': user_sk,
        'GSI1PK': gsi1pk,
        'GSI1SK': user_pk,
        'entityType': payload.get('entityType', 'User'),
        'email': email
    }

    for key, value in payload.items():
        if key in {'PK', 'SK', 'GSI1PK', 'GSI1SK'}:
            continue
        if key == 'id':
            continue
        item[key] = value

    try:
        create_cognito_user(user_pk, email, payload)
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        if error_code in {'UsernameExistsException', 'AliasExistsException'}:
            logger.warning('route=/Users method=%s cognito_duplicate=true pk=%s email=%s', request.method, user_pk, email)
            return create_response(409, {'message': f'Cognito user already exists for {user_pk}'})
        logger.exception('route=/Users method=%s cognito_client_error pk=%s email=%s', request.method, user_pk, email)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/Users method=%s cognito_unexpected_error pk=%s email=%s', request.method, user_pk, email)
        return create_response(500, {'message': str(e)})

    cognito_created = True
    try:
        table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
        )
        logger.info('route=/Users method=%s created=true pk=%s sk=%s', request.method, user_pk, user_sk)
        return create_response(201, item)
    except ClientError as e:
        if cognito_created:
            delete_cognito_user(user_pk)
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.warning('route=/Users method=%s duplicate=true pk=%s sk=%s', request.method, user_pk, user_sk)
            return create_response(409, {'message': f'User with PK {user_pk} and SK {user_sk} already exists'})
        logger.exception('route=/Users method=%s aws_client_error pk=%s sk=%s', request.method, user_pk, user_sk)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        if cognito_created:
            delete_cognito_user(user_pk)
        logger.exception('route=/Users method=%s unexpected_error pk=%s sk=%s', request.method, user_pk, user_sk)
        return create_response(500, {'message': str(e)})


@app.route('/Users/<id>', methods=['PATCH', 'PUT'])
def update_user(id):
    fields = request.get_json(silent=True) or {}
    logger.info('route=/Users/<id> method=%s id=%s payload_keys=%s', request.method, id, list(fields.keys()) if isinstance(fields, dict) else type(fields).__name__)

    if not id:
        return create_response(400, {'message': 'user id path parameter is required'})

    if not isinstance(fields, dict) or not fields:
        return create_response(400, {'message': 'Request body must be a non-empty JSON object'})

    # Do not allow key attributes to be changed.
    # "GSI1PK", "GSI1SK" can be channged indirectly by allowing email to be updated,
    # but PK and SK should be immutable after creation.
    forbidden = {'PK', 'SK', 'GSI1PK'}
    blocked = [k for k in fields.keys() if k in forbidden]
    if blocked:
        return create_response(400, {'message': f'Cannot update key attributes: {", ".join(blocked)}'})

    try:
        items = []
        matched_lookup_key = id

        # Allow updating by either user id (PK) or email (GSI1PK).
        if id.startswith('EMAIL#') or ('@' in id):
            email_keys = [id] if id.startswith('EMAIL#') else [f'EMAIL#{id}', id]
            for email_key in email_keys:
                lookup = table.query(
                    IndexName='GSI1',
                    KeyConditionExpression=Key('GSI1PK').eq(email_key),
                    Limit=1
                )
                items = lookup.get('Items', [])
                if items:
                    matched_lookup_key = email_key
                    break
        else:
            # Build the user's PK from path id, no table scan.
            # If your id already comes as USER#2, keep it as-is.
            user_pk = id if id.startswith('USER#') else f'USER#{id}'
            lookup = table.query(
                KeyConditionExpression=Key('PK').eq(user_pk),
                Limit=1
            )
            items = lookup.get('Items', [])
            matched_lookup_key = user_pk

        if not items:
            return create_response(404, {'message': f'User {id} does not exist'})

        item = items[0]
        user_pk = item.get('PK')
        sk = item.get('SK')
        if not user_pk or not sk:
            return create_response(500, {'message': 'Matched user record is missing PK or SK'})

        # Keep email lookup key aligned if caller updates email but omits GSI1PK.
        if 'email' in fields and 'GSI1PK' not in fields:
            email = fields.get('email')
            fields['GSI1PK'] = email if str(email).startswith('EMAIL#') else f'EMAIL#{email}'

        expression_attribute_names = {}
        expression_attribute_values = {}
        set_clauses = []

        for i, (key, value) in enumerate(fields.items()):
            name_key = f'#k{i}'
            value_key = f':v{i}'
            expression_attribute_names[name_key] = key
            expression_attribute_values[value_key] = value
            set_clauses.append(f'{name_key} = {value_key}')

        response = table.update_item(
            Key={'PK': user_pk, 'SK': sk},
            UpdateExpression='SET ' + ', '.join(set_clauses),
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ConditionExpression='attribute_exists(PK) AND attribute_exists(SK)',
            ReturnValues='ALL_NEW'
        )
        logger.info('route=/Users/<id> method=%s updated=true id=%s lookup_key=%s pk=%s', request.method, id, matched_lookup_key, user_pk)
        return create_response(200, response.get('Attributes', {}))

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.warning('route=/Users/<id> method=%s not_found=true id=%s', request.method, id)
            return create_response(404, {'message': f'User {id} does not exist'})
        logger.exception('route=/Users/<id> method=%s aws_client_error id=%s', request.method, id)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/Users/<id> method=%s unexpected_error id=%s', request.method, id)
        return create_response(500, {'message': str(e)})


@app.route('/Users/help')
def help_page():
    logger.info('route=/Users/help method=%s', request.method)
    docs_path = os.path.join(os.path.dirname(__file__), 'API_USAGE.md')

    if not os.path.exists(docs_path):
        logger.warning('route=/Users/help docs_missing path=%s', docs_path)
        return (
            '<h1>API Help</h1><p>API_USAGE.md was not found in the project folder.</p>',
            404,
        )

    with open(docs_path, 'r', encoding='utf-8') as f:
        markdown_text = f.read()

    try:
        md = __import__('markdown')
        content_html = md.markdown(
            markdown_text,
            extensions=['fenced_code', 'tables', 'toc']
        )
    except Exception:
        logger.info('route=/Users/help markdown_package_not_available_using_fallback=true')
        # content_html = _render_markdown_fallback(markdown_text)
    return render_template('help.html', content_html=content_html)


def create_response(status_code, body):
    # Normalize Decimal and other non-JSON-native values first
    payload = json.dumps(
        body,
        default=lambda x: float(x) if isinstance(x, Decimal) else str(x)
    )

    response = app.response_class(
        response=payload,
        status=status_code,
        mimetype='application/json'
    )
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

def create_cognito_user(user_pk, email, payload):
    if not cognito_user_pool_id:
        raise RuntimeError(cognito_setup_error or 'Cognito user pool is not configured')

    user_attributes = [
        {'Name': 'email', 'Value': str(email)},
        {'Name': 'email_verified', 'Value': 'false'},
    ]

    for attribute_name in ('name', 'given_name', 'family_name', 'phone_number', 'preferred_username'):
        attribute_value = payload.get(attribute_name)
        if attribute_value not in (None, ''):
            user_attributes.append({'Name': attribute_name, 'Value': str(attribute_value)})

    return cognito_client.admin_create_user(
        UserPoolId=cognito_user_pool_id,
        Username=str(user_pk),
        UserAttributes=user_attributes,
        MessageAction='SUPPRESS',
    )


def delete_cognito_user(user_pk):
    if not cognito_user_pool_id:
        return

    try:
        cognito_client.admin_delete_user(
            UserPoolId=cognito_user_pool_id,
            Username=str(user_pk),
        )
    except ClientError:
        logger.exception('cognito rollback failed username=%s', user_pk)



if __name__ == '__main__':
    app.run(debug=True)


