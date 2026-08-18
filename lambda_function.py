import os
import time
import boto3

client = boto3.client('cloudfront')
DISTRIBUTION_ID = os.environ['DISTRIBUTION_ID']

def lambda_handler(event, context):
    print("S3 Event received, triggering CloudFront invalidation...")
    
    # Paths to invalidate
    paths = ["/index.html", "/"]
    
    try:
        response = client.create_invalidation(
            DistributionId=DISTRIBUTION_ID,
            InvalidationBatch={
                'Paths': {
                    'Quantity': len(paths),
                    'Items': paths
                },
                'CallerReference': str(time.time())
            }
        )
        print(f"Invalidation created successfully: {response['Invalidation']['Id']}")
        return {
            'statusCode': 200,
            'body': 'Invalidation triggered successfully!'
        }
    except Exception as e:
        print(f"Error creating invalidation: {str(e)}")
        raise e