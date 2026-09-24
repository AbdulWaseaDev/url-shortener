# URL Shortener API - Postman Guide

## API Endpoint
```
https://url-shortener.berlintechs.com
```

## Quick Start - Import Collection

1. Open Postman
2. Click **Import** button (top left)
3. Select **File** tab
4. Choose `URL-Shortener.postman_collection.json`
5. Click **Import**

The collection includes all three endpoints pre-configured and ready to use!

**Set your API key:** creating links requires an API key. After importing, open the collection, go to the **Variables** tab and replace `YOUR_API_KEY` in `api_key` with your key. The collection sends it as the `x-api-key` header on "Create Short Link". Redirects and stats don't need a key.

---

## API Endpoints

### 1. Create Short Link

**POST** `/links`

**Request:**
```json
{
  "url": "https://example.com"
}
```

**Response:**
```json
{
  "short_code": "abc123",
  "short_url": "https://url-shortener.berlintechs.com/abc123",
  "original_url": "https://example.com"
}
```

**Postman Setup:**
- Method: `POST`
- URL: `https://url-shortener.berlintechs.com/links`
- Headers: `Content-Type: application/json`, `x-api-key: YOUR_API_KEY`
- Body (raw JSON):
  ```json
  {
    "url": "https://github.com/AbdulWaseaDev/url-shortener"
  }
  ```

---

### 2. Redirect to Original URL

**GET** `/{short_code}`

**Response:**
- HTTP 302 Redirect to the original URL
- Increments click counter

**Postman Setup:**
- Method: `GET`
- URL: `https://url-shortener.berlintechs.com/abc123`
- Replace `abc123` with your actual short code

**Note:** Postman will show the redirect response. To see the final URL, check the response headers or disable "Automatically follow redirects" in Postman settings.

---

### 3. Get Link Statistics

**GET** `/links/{short_code}/stats`

**Response:**
```json
{
  "short_code": "abc123",
  "original_url": "https://example.com",
  "clicks": 5,
  "created_at": "2026-09-15T12:00:00Z"
}
```

**Postman Setup:**
- Method: `GET`
- URL: `https://url-shortener.berlintechs.com/links/abc123/stats`
- Replace `abc123` with your actual short code

---

## Testing Workflow

1. **Create a link:**
   - Use the "Create Short Link" request
   - Copy the `short_code` from the response (e.g., `abc123`)

2. **Test the redirect:**
   - Use the "Redirect to Original URL" request
   - Replace `abc123` in the URL with your short code
   - You should see a 302 redirect

3. **Check statistics:**
   - Use the "Get Link Statistics" request
   - Replace `abc123` in the URL with your short code
   - You'll see the click count has incremented

---

## Error Responses

### 400 Bad Request
```json
{
  "error": "Missing url field"
}
```

### 403 Forbidden
Missing or invalid `x-api-key` on "Create Short Link":
```json
{
  "message": "Forbidden"
}
```

### 404 Not Found
```json
{
  "error": "Short link not found"
}
```

### 429 Too Many Requests
Rate limit or daily quota exceeded:
```json
{
  "message": "Too Many Requests"
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error"
}
```

---

## Tips

- **Save responses:** In Postman, save example responses for each endpoint
- **Environment variables:** Create a Postman environment with:
  - `base_url`: `https://url-shortener.berlintechs.com`
  - `api_key`: Your API key for creating links
  - `short_code`: Save this after creating a link
- **Tests:** Add Postman tests to validate responses automatically

Example Postman test for "Create Short Link":
```javascript
pm.test("Status code is 201", function () {
    pm.response.to.have.status(201);
});

pm.test("Response has short_code", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('short_code');
    pm.environment.set("short_code", jsonData.short_code);
});
```

---

## Architecture

- **API Gateway:** REST API with Lambda proxy integration
- **Lambda:** Python 3.13 runtime
- **DynamoDB:** Serverless NoSQL database (on-demand billing)
- **CloudWatch:** Automatic logging with 7-day retention
- **X-Ray:** Distributed tracing enabled
