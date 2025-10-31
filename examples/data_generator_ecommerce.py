#!/usr/bin/env python3
"""
E-commerce event data generator
Simulates realistic online shopping behavior
"""
import random
import time
import json
from datetime import datetime

products = [
    {"id": "prod_1", "name": "Laptop", "price": 999.99, "category": "Electronics"},
    {"id": "prod_2", "name": "Wireless Mouse", "price": 29.99, "category": "Electronics"},
    {"id": "prod_3", "name": "Mechanical Keyboard", "price": 79.99, "category": "Electronics"},
    {"id": "prod_4", "name": "4K Monitor", "price": 299.99, "category": "Electronics"},
    {"id": "prod_5", "name": "Noise-Cancelling Headphones", "price": 149.99, "category": "Audio"},
    {"id": "prod_6", "name": "Smartphone", "price": 699.99, "category": "Electronics"},
    {"id": "prod_7", "name": "Tablet", "price": 399.99, "category": "Electronics"},
    {"id": "prod_8", "name": "Webcam", "price": 59.99, "category": "Electronics"},
    {"id": "prod_9", "name": "USB-C Hub", "price": 39.99, "category": "Accessories"},
    {"id": "prod_10", "name": "Desk Lamp", "price": 45.99, "category": "Furniture"},
]

event_types = ["page_view", "add_to_cart", "remove_from_cart", "purchase", "search"]
users = [f"user_{i:04d}" for i in range(1, 101)]  # 100 users

def generate_ecommerce_events(events_per_second=10):
    """
    Generate realistic e-commerce events

    Args:
        events_per_second: Target event generation rate
    """
    session_carts = {}  # Track items in each user's cart

    while True:
        user = random.choice(users)
        product = random.choice(products)
        session_id = f"sess_{hash(user) % 10000}"

        # Initialize cart for new sessions
        if session_id not in session_carts:
            session_carts[session_id] = []

        # Realistic event distribution
        # Users browse (page_view) more than they add to cart
        # Users rarely remove items
        # Purchase is least frequent
        event_type = random.choices(
            event_types,
            weights=[50, 20, 3, 8, 19]
        )[0]

        # Initialize default values
        total_value = 0
        quantity = 1

        # Logic for cart operations
        if event_type == "add_to_cart":
            if product["id"] not in session_carts[session_id]:
                session_carts[session_id].append(product["id"])

        elif event_type == "remove_from_cart":
            if session_carts[session_id]:
                event_type = "remove_from_cart"
                product_id = random.choice(session_carts[session_id])
                session_carts[session_id].remove(product_id)
                product = next(p for p in products if p["id"] == product_id)
            else:
                event_type = "page_view"  # Can't remove from empty cart

        elif event_type == "purchase":
            if session_carts[session_id]:
                # Purchase all items in cart
                total_value = sum(
                    next(p["price"] for p in products if p["id"] == pid)
                    for pid in session_carts[session_id]
                )
                quantity = len(session_carts[session_id])
                session_carts[session_id] = []  # Clear cart
            else:
                # No cart items, convert to page view
                event_type = "page_view"

        event = {
            "event_id": f"evt_{int(time.time() * 1000000)}",
            "timestamp": int(time.time() * 1000),
            "user_id": user,
            "event_type": event_type,
            "product_id": product["id"],
            "product_name": product["name"],
            "price": product["price"],
            "category": product["category"],
            "quantity": quantity,
            "session_id": session_id,
            "cart_size": len(session_carts[session_id])
        }

        if event_type == "purchase":
            event["total_value"] = round(total_value, 2)

        yield event
        time.sleep(1.0 / events_per_second)

if __name__ == "__main__":
    print("# E-commerce Event Generator")
    print("# Generating events... (Ctrl+C to stop)")
    print()

    try:
        for event in generate_ecommerce_events(events_per_second=5):
            print(json.dumps(event))
    except KeyboardInterrupt:
        print("\nStopped.")
