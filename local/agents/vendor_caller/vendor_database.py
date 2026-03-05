"""
Vendor Database - Query vendors by product category from OpenSearch
"""

import boto3
from typing import List, Dict, Any
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth


class VendorDatabase:
    """Query and manage vendor information from OpenSearch"""
    
    def __init__(self):
        """Initialize OpenSearch connection"""
        credentials = boto3.Session().get_credentials()
        self.awsauth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            'us-east-1',
            'es',
            session_token=credentials.token
        )
        
        self.client = OpenSearch(
            hosts=[{
                'host': 'search-christmas-catalog-bcl77whynen7enbam5vr4rjgeu.us-east-1.es.amazonaws.com',
                'port': 443
            }],
            http_auth=self.awsauth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection
        )
        
        self.index = 'valentines-catalog'
    
    def get_vendors_for_product(self, product_name: str = None, category: str = None, 
                                sku: str = None) -> List[Dict[str, Any]]:
        """
        Get all vendors who supply a specific product or category
        
        Args:
            product_name: Product name to search for
            category: Product category
            sku: Product SKU
            
        Returns:
            List of vendors with their contact info, sorted by priority
        """
        try:
            # Build search query
            must_clauses = []
            
            if sku:
                must_clauses.append({'match': {'sku': sku}})
            if product_name:
                must_clauses.append({'match': {'name': product_name}})
            if category:
                must_clauses.append({'match': {'category': category}})
            
            # If no criteria provided, return empty
            if not must_clauses:
                print("Warning: No search criteria provided")
                return []
            
            query = {
                'query': {
                    'bool': {
                        'should': must_clauses,
                        'minimum_should_match': 1
                    }
                },
                'size': 100  # Get up to 100 products
            }
            
            response = self.client.search(index=self.index, body=query)
            
            # Extract unique vendors from results
            vendors_map = {}
            
            for hit in response['hits']['hits']:
                product = hit['_source']
                vendor_name = product.get('vendor_name') or product.get('vendor')
                
                if not vendor_name:
                    continue
                
                # Skip if we already have this vendor
                if vendor_name in vendors_map:
                    continue
                
                # Get vendor contact info
                vendor_phone = product.get('vendor_phone', '')
                vendor_email = product.get('vendor_email', '')
                vendor_priority = product.get('vendor_priority', 5)  # Default priority 5
                
                # Only add vendors with phone numbers
                if vendor_phone:
                    vendors_map[vendor_name] = {
                        'name': vendor_name,
                        'phone': vendor_phone,
                        'email': vendor_email,
                        'priority': vendor_priority,
                        'products_supplied': [product.get('name', '')],
                        'categories': [product.get('category', '')]
                    }
                else:
                    # Aggregate products for existing vendor
                    if vendor_name in vendors_map:
                        vendors_map[vendor_name]['products_supplied'].append(product.get('name', ''))
                        category = product.get('category', '')
                        if category and category not in vendors_map[vendor_name]['categories']:
                            vendors_map[vendor_name]['categories'].append(category)
            
            # Convert to list and sort by priority (lower number = higher priority)
            vendors = list(vendors_map.values())
            vendors.sort(key=lambda x: x['priority'])
            
            print(f"Found {len(vendors)} vendors for product/category")
            for v in vendors:
                print(f"  - {v['name']} (priority: {v['priority']}, phone: {v['phone']})")
            
            return vendors
            
        except Exception as e:
            print(f"Error querying vendors: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_vendor_by_name(self, vendor_name: str) -> Dict[str, Any]:
        """
        Get specific vendor details by name
        
        Args:
            vendor_name: Name of the vendor
            
        Returns:
            Vendor details or None if not found
        """
        try:
            query = {
                'query': {
                    'match': {'vendor_name': vendor_name}
                },
                'size': 1
            }
            
            response = self.client.search(index=self.index, body=query)
            
            if response['hits']['total']['value'] > 0:
                product = response['hits']['hits'][0]['_source']
                return {
                    'name': product.get('vendor_name') or product.get('vendor'),
                    'phone': product.get('vendor_phone', ''),
                    'email': product.get('vendor_email', ''),
                    'priority': product.get('vendor_priority', 5)
                }
            
            return None
            
        except Exception as e:
            print(f"Error getting vendor by name: {e}")
            return None
    
    def get_all_vendors(self) -> List[Dict[str, Any]]:
        """
        Get all unique vendors in the system
        
        Returns:
            List of all vendors
        """
        try:
            query = {
                'query': {'match_all': {}},
                'size': 1000
            }
            
            response = self.client.search(index=self.index, body=query)

            vendors_map = {}
            for hit in response['hits']['hits']:
                product = hit['_source']
                vendor_name = product.get('vendor_name') or product.get('vendor')

                if vendor_name and vendor_name not in vendors_map:
                    vendor_phone = product.get('vendor_phone', '')
                    # Include all vendors, but keep phone optional so UI can show
                    # the full directory even if some vendors are not callable yet.
                    vendors_map[vendor_name] = {
                        'name': vendor_name,
                        'phone': vendor_phone,
                        'email': product.get('vendor_email', ''),
                        'priority': product.get('vendor_priority', 5)
                    }
            
            vendors = list(vendors_map.values())
            vendors.sort(key=lambda x: x['name'])
            
            return vendors
            
        except Exception as e:
            print(f"Error getting all vendors: {e}")
            return []
    
    def add_test_vendor_phone(self, vendor_name: str, phone: str):
        """
        Helper method to add phone number to vendor products (for testing)
        Note: This updates all products from this vendor
        """
        try:
            # Find all products from this vendor
            query = {
                'query': {
                    'match': {'vendor_name': vendor_name}
                },
                'size': 100
            }
            
            response = self.client.search(index=self.index, body=query)
            
            updated_count = 0
            for hit in response['hits']['hits']:
                doc_id = hit['_id']
                
                # Update document with phone number
                update_body = {
                    'doc': {
                        'vendor_phone': phone
                    }
                }
                
                self.client.update(
                    index=self.index,
                    id=doc_id,
                    body=update_body
                )
                updated_count += 1
            
            print(f"Updated {updated_count} products for vendor {vendor_name} with phone {phone}")
            return updated_count
            
        except Exception as e:
            print(f"Error adding vendor phone: {e}")
            return 0


# Convenience functions
def get_vendors_for_category(category: str) -> List[Dict[str, Any]]:
    """Quick function to get vendors by category"""
    db = VendorDatabase()
    return db.get_vendors_for_product(category=category)


def get_vendors_for_product_name(product_name: str) -> List[Dict[str, Any]]:
    """Quick function to get vendors by product name"""
    db = VendorDatabase()
    return db.get_vendors_for_product(product_name=product_name)


if __name__ == '__main__':
    # Test the vendor database
    print("=" * 70)
    print("VENDOR DATABASE TEST")
    print("=" * 70)
    print()
    
    db = VendorDatabase()
    
    # Test 1: Get vendors for a category
    print("Test 1: Get vendors for 'Ornaments' category")
    vendors = db.get_vendors_for_product(category='Ornaments')
    print(f"Found {len(vendors)} vendors")
    for v in vendors[:3]:  # Show first 3
        print(f"  - {v['name']}: {v['phone']}")
    print()
    
    # Test 2: Get all vendors
    print("Test 2: Get all vendors")
    all_vendors = db.get_all_vendors()
    print(f"Total vendors in system: {len(all_vendors)}")
    for v in all_vendors[:5]:  # Show first 5
        print(f"  - {v['name']}: {v['phone']}")
    print()
    
    # Test 3: Get vendors for specific product
    print("Test 3: Get vendors for 'Valentine Ornaments'")
    vendors = db.get_vendors_for_product(product_name='Valentine Ornaments')
    print(f"Found {len(vendors)} vendors")
    for v in vendors:
        print(f"  - {v['name']}: {v['phone']} (priority: {v['priority']})")
