def get_token(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    return response.json()["access_token"]

def test_get_cart_unauthorized(client):
    response = client.get("/api/cart/")
    # Since require_current_user throws 401 if token is missing
    assert response.status_code == 401

def test_add_and_get_cart_item(client, test_user, test_product):
    token = get_token(client, test_user.email, "password123")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Add an item to the cart
    add_response = client.post(
        "/api/cart/",
        json={
            "product_id": 101,
            "size": "L",
            "quantity": 2
        },
        headers=headers
    )
    assert add_response.status_code == 200
    
    # Retrieve the cart
    get_response = client.get("/api/cart/", headers=headers)
    assert get_response.status_code == 200
    cart_items = get_response.json()
    
    assert len(cart_items) == 1
    assert cart_items[0]["product_id"] == 101
    assert cart_items[0]["size"] == "L"
    assert cart_items[0]["quantity"] == 2

def test_remove_cart_item(client, test_user, test_product):
    token = get_token(client, test_user.email, "password123")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Add an item first
    client.post(
        "/api/cart/",
        json={"product_id": 102, "size": "M", "quantity": 1},
        headers=headers
    )
    
    # Get the cart to find the cart item ID
    cart_items = client.get("/api/cart/", headers=headers).json()
    item_id = cart_items[0]["id"]
    
    # Remove it
    remove_response = client.delete(f"/api/cart/{item_id}", headers=headers)
    assert remove_response.status_code == 200
    
    # Verify cart is empty
    empty_cart = client.get("/api/cart/", headers=headers).json()
    assert len(empty_cart) == 0
