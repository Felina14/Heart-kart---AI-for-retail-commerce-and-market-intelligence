#!/usr/bin/env python3
"""
Unified Product Data Access Layer
Provides a consistent interface for accessing products from DynamoDB
Supports both DynamoDB (primary) and OpenSearch (fallback)
"""

import boto3
import os
from typing import Dict, List, Optional, Any
from decimal import Decimal
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr

# DynamoDB configuration
REGION = os.environ.get('AWS_REGION', 'us-east-1')
TABLE_NAME = os.environ.get('PRODUCTS_TABLE_NAME', 'valentines-products')

dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

# OpenSearch fallback (optional)
OPENSEARCH_ENABLED = os.environ.get('OPENSEARCH_ENABLED', 'false').lower() == 'true'
opensearch_client = None

if OPENSEARCH_ENABLED:
    try:
        from opensearchpy import OpenSearch, RequestsHttpConnection
        from requests_aws4auth import AWS4Auth
        
        OPENSEARCH_ENDPOINT = os.environ.get(
            'OPENSEARCH_ENDPOINT',
            'search-christmas-catalog-bcl77whynen7enbam5vr4rjgeu.us-east-1.es.amazonaws.com'
        )
        
        credentials = boto3.Session().get_credentials()
        awsauth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            REGION,
            'es',
            session_token=credentials.token
        )
        
        opensearch_client = OpenSearch(
            hosts=[{'host': OPENSEARCH_ENDPOINT, 'port': 443}],
            http_auth=awsauth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection
        )
    except Exception as e:
        print(f"Warning: OpenSearch fallback not available: {e}")
        opensearch_client = None


def decimal_to_float(obj):
    """Convert Decimal types to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    return obj


def get_product_by_sku(sku: str) -> Optional[Dict]:
    """Get a single product by SKU"""
    try:
        response = table.get_item(Key={'sku': sku})
        if 'Item' in response:
            item = response['Item']
            # Convert Decimal to float for compatibility
            return decimal_to_float(item)
        return None
    except ClientError as e:
        print(f"Error getting product {sku}: {e}")
        return None


def get_all_products(limit: int = 10000) -> List[Dict]:
    """Get all products from DynamoDB"""
    try:
        products = []
        response = table.scan(Limit=limit)
        products.extend(response.get('Items', []))
        
        # Handle pagination
        while 'LastEvaluatedKey' in response and len(products) < limit:
            response = table.scan(
                Limit=limit - len(products),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            products.extend(response.get('Items', []))
        
        # Convert Decimal to float
        return decimal_to_float(products)
    except ClientError as e:
        print(f"Error getting all products: {e}")
        # Fallback to OpenSearch if available
        if opensearch_client:
            return get_all_products_opensearch(limit)
        return []


def get_products_by_category(category: str, limit: int = 1000) -> List[Dict]:
    """Get products by category using GSI"""
    try:
        response = table.query(
            IndexName='category-index',
            KeyConditionExpression=Key('category').eq(category),
            Limit=limit
        )
        
        products = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response and len(products) < limit:
            response = table.query(
                IndexName='category-index',
                KeyConditionExpression=Key('category').eq(category),
                Limit=limit - len(products),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            products.extend(response.get('Items', []))
        
        return decimal_to_float(products)
    except ClientError as e:
        print(f"Error getting products by category {category}: {e}")
        return []


def get_products_by_vendor(vendor_name: str, limit: int = 1000) -> List[Dict]:
    """Get products by vendor using GSI"""
    try:
        response = table.query(
            IndexName='vendor-index',
            KeyConditionExpression=Key('vendor_name').eq(vendor_name),
            Limit=limit
        )
        
        products = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response and len(products) < limit:
            response = table.query(
                IndexName='vendor-index',
                KeyConditionExpression=Key('vendor_name').eq(vendor_name),
                Limit=limit - len(products),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            products.extend(response.get('Items', []))
        
        return decimal_to_float(products)
    except ClientError as e:
        print(f"Error getting products by vendor {vendor_name}: {e}")
        return []


def get_low_stock_products(threshold: Optional[int] = None, limit: int = 1000) -> List[Dict]:
    """Get products below reorder point or custom threshold"""
    try:
        if threshold is None:
            # Get products below their reorder point
            response = table.scan(
                FilterExpression=Attr('stock_quantity').lt(Attr('reorder_point')),
                Limit=limit
            )
        else:
            # Get products below custom threshold
            response = table.scan(
                FilterExpression=Attr('stock_quantity').lt(threshold),
                Limit=limit
            )
        
        products = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response and len(products) < limit:
            if threshold is None:
                response = table.scan(
                    FilterExpression=Attr('stock_quantity').lt(Attr('reorder_point')),
                    Limit=limit - len(products),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
            else:
                response = table.scan(
                    FilterExpression=Attr('stock_quantity').lt(threshold),
                    Limit=limit - len(products),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
            products.extend(response.get('Items', []))
        
        # Sort by stock_quantity ascending
        products.sort(key=lambda x: x.get('stock_quantity', 0))
        
        return decimal_to_float(products)
    except ClientError as e:
        print(f"Error getting low stock products: {e}")
        return []


def search_products(query: str, limit: int = 100) -> List[Dict]:
    """Search products by name (simple contains search)"""
    try:
        # DynamoDB doesn't support full-text search, so we scan and filter
        # For better performance, consider using OpenSearch for search
        all_products = get_all_products(limit=5000)  # Get a reasonable subset
        
        # Simple case-insensitive search
        query_lower = query.lower()
        results = [
            p for p in all_products
            if query_lower in p.get('name', '').lower() or 
               query_lower in p.get('sku', '').lower() or
               query_lower in p.get('category', '').lower()
        ]
        
        return results[:limit]
    except Exception as e:
        print(f"Error searching products: {e}")
        return []


def get_all_products_opensearch(limit: int = 10000) -> List[Dict]:
    """Fallback: Get products from OpenSearch"""
    if not opensearch_client:
        return []
    
    try:
        response = opensearch_client.search(
            index='valentines-catalog',
            body={
                'query': {'match_all': {}},
                'size': min(limit, 10000)
            }
        )
        
        products = []
        for hit in response['hits']['hits']:
            product = hit['_source']
            # Map vendor_name to vendor for compatibility
            if 'vendor_name' in product and 'vendor' not in product:
                product['vendor'] = product['vendor_name']
            products.append(product)
        
        return products
    except Exception as e:
        print(f"Error getting products from OpenSearch: {e}")
        return []


def format_product_for_frontend(product: Dict) -> Dict:
    """Format product data for frontend compatibility"""
    # Ensure all expected fields exist
    formatted = {
        'sku': product.get('sku', 'N/A'),
        'name': product.get('name', 'Unknown'),
        'category': product.get('category', 'Uncategorized'),
        'vendor': product.get('vendor_name', product.get('vendor', 'Unknown')),
        'vendor_name': product.get('vendor_name', product.get('vendor', 'Unknown')),
        'price': float(product.get('price', 0)),
        'stock_quantity': int(product.get('stock_quantity', product.get('inventory', 0))),
        'inventory': int(product.get('inventory', product.get('stock_quantity', 0))),
        'reorder_point': int(product.get('reorder_point', 10)),
        'sales_velocity': float(product.get('sales_velocity', 0)),
        'rating': float(product.get('rating', 0)),
        'currency': product.get('currency', 'INR'),
        'delivery_options': product.get('delivery_options', []),
        'personalizable': product.get('personalizable', False),
        'created_at': product.get('created_at', ''),
        # Vendor fields
        'vendor_phone': product.get('vendor_phone', ''),
        'vendor_email': product.get('vendor_email', ''),
        'vendor_priority': product.get('vendor_priority', 3),
        'vendor_lead_time_days': product.get('vendor_lead_time_days', product.get('lead_time_days', 7)),
        'vendor_moq': product.get('vendor_moq', 50),
        'vendor_on_time_rate': float(product.get('vendor_on_time_rate', 0.9)),
        # Additional fields
        'lead_time_days': product.get('lead_time_days', product.get('vendor_lead_time_days', 7)),
        'last_restock_date': product.get('last_restock_date', ''),
        'in_stock': product.get('in_stock', product.get('stock_quantity', 0) > 0),
        'category_id': product.get('category_id', 0)
    }
    
    return formatted


def get_inventory_for_frontend(limit: int = 10000) -> Dict:
    """Get all inventory formatted for frontend"""
    products = get_all_products(limit=limit)
    
    formatted_products = [format_product_for_frontend(p) for p in products]
    
    return {
        'success': True,
        'count': len(formatted_products),
        'inventory': formatted_products
    }


def get_product_count() -> int:
    """Get total product count"""
    try:
        response = table.scan(Select='COUNT')
        count = response.get('Count', 0)
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                Select='COUNT',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            count += response.get('Count', 0)
        
        return count
    except ClientError as e:
        print(f"Error getting product count: {e}")
        return 0
