# Scrape API

Extract structured JSON from a fully rendered page using CSS selectors. Each request must include a `url` and an `elements` array that lists the selectors you want to capture.

**Endpoint**

- Method: POST
- Path: /scrape
- Auth: token query parameter (?token=)
- Content-Type: application/json
- Response: application/json

See the [OpenAPI reference](https://docs.browserless.io/open-api#tag/Browser-REST-APIs/paths/~1chrome~1scrape/post) for complete details.

## Quickstart​

- cURL
- Javascript
- Python
- Java
- C#

```
curl --request POST \  --url 'https://production-sfo.browserless.io/scrape?token=YOUR_API_TOKEN_HERE' \  --header 'content-type: application/json' \  --data '{  "url": "https://browserless.io/",  "elements": [    {      "selector": "h1"    }  ]}'
```

```
const TOKEN = "YOUR_API_TOKEN_HERE";const url = `https://production-sfo.browserless.io/scrape?token=${TOKEN}`;const headers = {  "Cache-Control": "no-cache",  "Content-Type": "application/json"};const data = {  url: "https://browserless.io/",  elements: [    { selector: "h1" }  ]};const scrapeContent = async () => {  const response = await fetch(url, {    method: 'POST',    headers: headers,    body: JSON.stringify(data)  });  const result = await response.json();  console.log(result);};scrapeContent();
```

```
import requestsTOKEN = "YOUR_API_TOKEN_HERE"url = f"https://production-sfo.browserless.io/scrape?token={TOKEN}"headers = {    "Cache-Control": "no-cache",    "Content-Type": "application/json"}data = {    "url": "https://browserless.io/",    "elements": [        { "selector": "h1" }    ]}response = requests.post(url, headers=headers, json=data)result = response.json()print(result)
```

```
import java.io.*;import java.net.URI;import java.net.http.*;public class ScrapeContent {    public static void main(String[] args) {        String TOKEN = "YOUR_API_TOKEN_HERE";        String url = "https://production-sfo.browserless.io/scrape?token=" + TOKEN;        String jsonData = """        {            "url": "https://browserless.io/",            "elements": [                { "selector": "h1" }            ]        }        """;        HttpClient client = HttpClient.newHttpClient();        HttpRequest request = HttpRequest.newBuilder()            .uri(URI.create(url))            .header("Cache-Control", "no-cache")            .header("Content-Type", "application/json")            .POST(HttpRequest.BodyPublishers.ofString(jsonData))            .build();        try {            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());            System.out.println("Response: " + response.body());        } catch (Exception e) {            e.printStackTrace();        }    }}
```

```
using System;using System.Net.Http;using System.Text;using System.Text.Json;using System.Threading.Tasks;class Program {    static async Task Main(string[] args) {        string TOKEN = "YOUR_API_TOKEN_HERE";        string url = $"https://production-sfo.browserless.io/scrape?token={TOKEN}";        string jsonData = @"        {            ""url"": ""https://browserless.io/"",            ""elements"": [                { ""selector"": ""h1"" }            ]        }";        using var client = new HttpClient();        var content = new StringContent(jsonData, Encoding.UTF8, "application/json");        try {            var response = await client.PostAsync(url, content);            response.EnsureSuccessStatusCode();            var result = await response.Content.ReadAsStringAsync();            Console.WriteLine("Response: " + result);        } catch (Exception ex) {            Console.WriteLine($"Error: {ex.Message}");        }    }}
```

**Response**

```
{  "data": [    {      "results": [        {          "attributes": [            { "name": "class", "value": "..." }          ],          "height": 120,          "html": "Headless browser automation, without the hosting headaches",          "left": 32,          "text": "Headless browser automation, without the hosting headaches",          "top": 196,          "width": 736        }      ],      "selector": "h1"    }  ]}
```

## How scraping works​

BrowserQL

We recommend using [BrowserQL](https://docs.browserless.io/browserql/start), Browserless' first-class browser automation API, to scrape content from any website.

The API uses `document.querySelectorAll` under the hood. Browserless loads the page, runs client-side JavaScript, and then waits (up to 30 seconds by default) for your selectors before scraping. Use more specific selectors to narrow down results.

### Specifying Page-Load Behavior​

The scrape API allows for setting specific page-load behaviors by setting a `gotoOptions` in the JSON body. This is passed directly into [puppeteer's goto() method](https://pptr.dev/api/puppeteer.page.goto).

In the example below, we'll set a `waitUntil` property and a `timeout`.

- cURL
- Javascript
- Python
- Java
- C#

```
curl --request POST \  --url 'https://production-sfo.browserless.io/scrape?token=YOUR_API_TOKEN_HERE' \  --header 'content-type: application/json' \  --data '{  "url": "https://example.com/",  "elements": [    {      "selector": "h1"    }  ],  "gotoOptions": {    "timeout": 10000,    "waitUntil": "networkidle2"  }}'
```

```
const TOKEN = "YOUR_API_TOKEN_HERE";const url = `https://production-sfo.browserless.io/scrape?token=${TOKEN}`;const headers = {  "Cache-Control": "no-cache",  "Content-Type": "application/json"};const data = {  url: "https://example.com/",  elements: [    { selector: "h1" }  ],  gotoOptions: {    timeout: 10000,    waitUntil: "networkidle2"  }};const scrapeContent = async () => {  const response = await fetch(url, {    method: 'POST',    headers: headers,    body: JSON.stringify(data)  });  const result = await response.json();  console.log(result);};scrapeContent();
```

```
import requestsTOKEN = "YOUR_API_TOKEN_HERE"url = f"https://production-sfo.browserless.io/scrape?token={TOKEN}"headers = {    "Cache-Control": "no-cache",    "Content-Type": "application/json"}data = {    "url": "https://example.com/",    "elements": [        { "selector": "h1" }    ],    "gotoOptions": {        "timeout": 10000,        "waitUntil": "networkidle2"    }}response = requests.post(url, headers=headers, json=data)result = response.json()print(result)
```

```
import java.io.*;import java.net.URI;import java.net.http.*;public class ScrapeContentWithOptions {    public static void main(String[] args) {        String TOKEN = "YOUR_API_TOKEN_HERE";        String url = "https://production-sfo.browserless.io/scrape?token=" + TOKEN;        String jsonData = """        {            "url": "https://example.com/",            "elements": [                { "selector": "h1" }            ],            "gotoOptions": {                "timeout": 10000,                "waitUntil": "networkidle2"            }        }        """;        HttpClient client = HttpClient.newHttpClient();        HttpRequest request = HttpRequest.newBuilder()            .uri(URI.create(url))            .header("Cache-Control", "no-cache")            .header("Content-Type", "application/json")            .POST(HttpRequest.BodyPublishers.ofString(jsonData))            .build();        try {            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());            System.out.println("Response: " + response.body());        } catch (Exception e) {            e.printStackTrace();        }    }}
```

```
using System;using System.Net.Http;using System.Text;using System.Text.Json;using System.Threading.Tasks;class Program {    static async Task Main(string[] args) {        string TOKEN = "YOUR_API_TOKEN_HERE";        string url = $"https://production-sfo.browserless.io/scrape?token={TOKEN}";        string jsonData = @"        {            ""url"": ""https://example.com/"",            ""elements"": [                { ""selector"": ""h1"" }            ],            ""gotoOptions"": {                ""timeout"": 10000,                ""waitUntil"": ""networkidle2""            }        }";        using var client = new HttpClient();        var content = new StringContent(jsonData, Encoding.UTF8, "application/json");        try {            var response = await client.PostAsync(url, content);            response.EnsureSuccessStatusCode();            var result = await response.Content.ReadAsStringAsync();            Console.WriteLine("Response: " + result);        } catch (Exception ex) {            Console.WriteLine($"Error: {ex.Message}");        }    }}
```

## Custom behavior with waitFor options​

Sometimes it's helpful to do further actions, or wait for custom events on the page before getting data. We allow this behavior with the `waitFor` properties.

### waitForTimeout​

Use `waitForTimeout` to pause for a fixed number of milliseconds before scraping.

- cURL
- Javascript
- Python
- Java
- C#

```
curl --request POST \  --url 'https://production-sfo.browserless.io/scrape?token=YOUR_API_TOKEN_HERE' \  --header 'content-type: application/json' \  --data '{  "url": "https://example.com/",  "elements": [    {      "selector": "h1"    }  ],  "waitForTimeout": 1000}'
```

```
const TOKEN = "YOUR_API_TOKEN_HERE";const url = `https://production-sfo.browserless.io/scrape?token=${TOKEN}`;const headers = {  "Cache-Control": "no-cache",  "Content-Type": "application/json"};const data = {  url: "https://example.com/",  elements: [    { selector: "h1" }  ],  waitForTimeout: 1000};const scrapeContent = async () => {  const response = await fetch(url, {    method: 'POST',    headers: headers,    body: JSON.stringify(data)  });  const result = await response.json();  console.log(result);};scrapeContent();
```

```
import requestsTOKEN = "YOUR_API_TOKEN_HERE"url = f"https://production-sfo.browserless.io/scrape?token={TOKEN}"headers = {    "Cache-Control": "no-cache",    "Content-Type": "application/json"}data = {    "url": "https://example.com/",    "elements": [        { "selector": "h1" }    ],    "waitForTimeout": 1000}response = requests.post(url, headers=headers, json=data)result = response.json()print(result)
```

```
import java.io.*;import java.net.URI;import java.net.http.*;public class ScrapeContentWithTimeout {    public static void main(String[] args) {        String TOKEN = "YOUR_API_TOKEN_HERE";        String url = "https://production-sfo.browserless.io/scrape?token=" + TOKEN;        String jsonData = """        {            "url": "https://example.com/",            "elements": [                { "selector": "h1" }            ],            "waitForTimeout": 1000        }        """;        HttpClient client = HttpClient.newHttpClient();        HttpRequest request = HttpRequest.newBuilder()            .uri(URI.create(url))            .header("Cache-Control", "no-cache")            .header("Content-Type", "application/json")            .POST(HttpRequest.BodyPublishers.ofString(jsonData))            .build();        try {            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());            System.out.println("Response: " + response.body());        } catch (Exception e) {            e.printStackTrace();        }    }}
```

```
using System;using System.Net.Http;using System.Text;using System.Text.Json;using System.Threading.Tasks;class Program {    static async Task Main(string[] args) {        string TOKEN = "YOUR_API_TOKEN_HERE";        string url = $"https://production-sfo.browserless.io/scrape?token={TOKEN}";        string jsonData = @"        {            ""url"": ""https://example.com/"",            ""elements"": [                { ""selector"": ""h1"" }            ],            ""waitForTimeout"": 1000        }";        using var client = new HttpClient();        var content = new StringContent(jsonData, Encoding.UTF8, "application/json");        try {            var response = await client.PostAsync(url, content);            response.EnsureSuccessStatusCode();            var result = await response.Content.ReadAsStringAsync();            Console.WriteLine("Response: " + result);        } catch (Exception ex) {            Console.WriteLine($"Error: {ex.Message}");        }    }}
```

### waitForSelector​

Use `waitForSelector` to wait for an element to appear before scraping. If the selector already exists, the method returns immediately. If the selector doesn't appear within the timeout, the request throws an exception.

#### Example​

- cURL
- Javascript
- Python
- Java
- C#

```
curl --request POST \  --url 'https://production-sfo.browserless.io/scrape?token=YOUR_API_TOKEN_HERE' \  --header 'content-type: application/json' \  --data '{  "url": "https://example.com/",  "elements": [    {      "selector": "h1"    }  ],  "waitForSelector": {    "selector": "h1",    "timeout": 5000  }}'
```

```
const TOKEN = "YOUR_API_TOKEN_HERE";const url = `https://production-sfo.browserless.io/scrape?token=${TOKEN}`;const headers = {  "Cache-Control": "no-cache",  "Content-Type": "application/json"};const data = {  url: "https://example.com/",  elements: [    { selector: "h1" }  ],  waitForSelector: {    selector: "h1",    timeout: 5000  }};const scrapeContent = async () => {  const response = await fetch(url, {    method: 'POST',    headers: headers,    body: JSON.stringify(data)  });  const result = await response.json();  console.log(result);};scrapeContent();
```

```
import requestsTOKEN = "YOUR_API_TOKEN_HERE"url = f"https://production-sfo.browserless.io/scrape?token={TOKEN}"headers = {    "Cache-Control": "no-cache",    "Content-Type": "application/json"}data = {    "url": "https://example.com/",    "elements": [        { "selector": "h1" }    ],    "waitForSelector": {        "selector": "h1",        "timeout": 5000    }}response = requests.post(url, headers=headers, json=data)result = response.json()print(result)
```

```
import java.io.*;import java.net.URI;import java.net.http.*;public class ScrapeContentWithWaitForSelector {    public static void main(String[] args) {        String TOKEN = "YOUR_API_TOKEN_HERE";        String url = "https://production-sfo.browserless.io/scrape?token=" + TOKEN;        String jsonData = """        {            "url": "https://example.com/",            "elements": [                { "selector": "h1" }            ],            "waitForSelector": {                "selector": "h1",                "timeout": 5000            }        }        """;        HttpClient client = HttpClient.newHttpClient();        HttpRequest request = HttpRequest.newBuilder()            .uri(URI.create(url))            .header("Cache-Control", "no-cache")            .header("Content-Type", "application/json")            .POST(HttpRequest.BodyPublishers.ofString(jsonData))            .build();        try {            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());            System.out.println("Response: " + response.body());        } catch (Exception e) {            e.printStackTrace();        }    }}
```

```
using System;using System.Net.Http;using System.Text;using System.Text.Json;using System.Threading.Tasks;class Program {    static async Task Main(string[] args) {        string TOKEN = "YOUR_API_TOKEN_HERE";        string url = $"https://production-sfo.browserless.io/scrape?token={TOKEN}";        string jsonData = @"        {            ""url"": ""https://example.com/"",            ""elements"": [                { ""selector"": ""h1"" }            ],            ""waitForSelector"": {                ""selector"": ""h1"",                ""timeout"": 5000            }        }";        using var client = new HttpClient();        var content = new StringContent(jsonData, Encoding.UTF8, "application/json");        try {            var response = await client.PostAsync(url, content);            response.EnsureSuccessStatusCode();            var result = await response.Content.ReadAsStringAsync();            Console.WriteLine("Response: " + result);        } catch (Exception ex) {            Console.WriteLine($"Error: {ex.Message}");        }    }}
```

### waitForFunction​

Use `waitForFunction` to run custom JavaScript on the page and wait until it finishes before scraping. The function can be any valid JS function, including `async` functions.

#### Example​

**JS function**

```
async () => {  const res = await fetch('https://jsonplaceholder.typicode.com/todos/1');  const json = await res.json();  document.querySelector("h1").innerText = json.title;}
```

- JSON payload
- cURL
- Javascript
- Python
- Java
- C#

```
{  "url": "https://example.com/",  "elements": [    { "selector": "h1" }  ],  "waitForFunction": {    "fn": "async()=>{let t=await fetch('https://jsonplaceholder.typicode.com/todos/1'),e=await t.json();document.querySelector('h1').innerText=e.title}",    "timeout": 5000  }}
```

```
curl --request POST \  --url 'https://production-sfo.browserless.io/scrape?token=YOUR_API_TOKEN_HERE' \  --header 'content-type: application/json' \  --data '{  "url": "https://example.com/",  "elements": [    {      "selector": "h1"    }  ],  "waitForFunction": {    "fn": "async()=>{let t=await fetch('\''https://jsonplaceholder.typicode.com/todos/1'\''),e=await t.json();document.querySelector('\''h1'\'').innerText=e.title}",    "timeout": 5000  }}'
```

```
const TOKEN = "YOUR_API_TOKEN_HERE";const url = `https://production-sfo.browserless.io/scrape?token=${TOKEN}`;const headers = {  "Cache-Control": "no-cache",  "Content-Type": "application/json"};const data = {  url: "https://example.com/",  elements: [    { selector: "h1" }  ],  waitForFunction: {    fn: "async()=>{let t=await fetch('https://jsonplaceholder.typicode.com/todos/1'),e=await t.json();document.querySelector('h1').innerText=e.title}",    timeout: 5000  }};const scrapeContent = async () => {  const response = await fetch(url, {    method: 'POST',    headers: headers,    body: JSON.stringify(data)  });  const result = await response.json();  console.log(result);};scrapeContent();
```

```
import requestsTOKEN = "YOUR_API_TOKEN_HERE"url = f"https://production-sfo.browserless.io/scrape?token={TOKEN}"headers = {    "Cache-Control": "no-cache",    "Content-Type": "application/json"}data = {    "url": "https://example.com/",    "elements": [        { "selector": "h1" }    ],    "waitForFunction": {        "fn": "async()=>{let t=await fetch('https://jsonplaceholder.typicode.com/todos/1'),e=await t.json();document.querySelector('h1').innerText=e.title}",        "timeout": 5000    }}response = requests.post(url, headers=headers, json=data)result = response.json()print(result)
```

```
import java.io.*;import java.net.URI;import java.net.http.*;public class ScrapeContentWithWaitForFunction {    public static void main(String[] args) {        String TOKEN = "YOUR_API_TOKEN_HERE";        String url = "https://production-sfo.browserless.io/scrape?token=" + TOKEN;        String jsonData = """        {            "url": "https://example.com/",            "elements": [                { "selector": "h1" }            ],            "waitForFunction": {                "fn": "async()=>{let t=await fetch('https://jsonplaceholder.typicode.com/todos/1'),e=await t.json();document.querySelector('h1').innerText=e.title}",                "timeout": 5000            }        }        """;        HttpClient client = HttpClient.newHttpClient();        HttpRequest request = HttpRequest.newBuilder()            .uri(URI.create(url))            .header("Cache-Control", "no-cache")            .header("Content-Type", "application/json")            .POST(HttpRequest.BodyPublishers.ofString(jsonData))            .build();        try {            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());            System.out.println("Response: " + response.body());        } catch (Exception e) {            e.printStackTrace();        }    }}
```

```
using System;using System.Net.Http;using System.Text;using System.Text.Json;using System.Threading.Tasks;class Program {    static async Task Main(string[] args) {        string TOKEN = "YOUR_API_TOKEN_HERE";        string url = $"https://production-sfo.browserless.io/scrape?token={TOKEN}";        string jsonData = @"        {            ""url"": ""https://example.com/"",            ""elements"": [                { ""selector"": ""h1"" }            ],            ""waitForFunction"": {                ""fn"": ""async()=>{let t=await fetch('https://jsonplaceholder.typicode.com/todos/1'),e=await t.json();document.querySelector('h1').innerText=e.title}"",                ""timeout"": 5000            }        }";        using var client = new HttpClient();        var content = new StringContent(jsonData, Encoding.UTF8, "application/json");        try {            var response = await client.PostAsync(url, content);            response.EnsureSuccessStatusCode();            var result = await response.Content.ReadAsStringAsync();            Console.WriteLine("Response: " + result);        } catch (Exception ex) {            Console.WriteLine($"Error: {ex.Message}");        }    }}
```

### waitForEvent​

Use `waitForEvent` to wait for a custom event that your application dispatches before scraping. This is useful for Single Page Applications (SPAs) that signal when they're ready.

#### Example​

- JSON payload
- cURL
- Javascript
- Python
- Java
- C#

```
{  "url": "https://example.com",  "elements": [    { "selector": "a" }  ],  "addScriptTag": [{    "content": "setTimeout(() => document.dispatchEvent(new CustomEvent('app:ready', { detail: { status: 'loaded' } })), 250);"  }],  "waitForEvent": {    "event": "app:ready",    "timeout": 1000  }}
```

```
curl --request POST \  --url 'https://production-sfo.browserless.io/scrape?token=YOUR_API_TOKEN_HERE' \  --header 'content-type: application/json' \  --data '{  "url": "https://example.com",  "elements": [    { "selector": "a" }  ],  "addScriptTag": [{    "content": "setTimeout(() => document.dispatchEvent(new CustomEvent('\''app:ready'\'', { detail: { status: '\''loaded'\'' } })), 250);"  }],  "waitForEvent": {    "event": "app:ready",    "timeout": 1000  }}'
```

```
const TOKEN = "YOUR_API_TOKEN_HERE";const url = `https://production-sfo.browserless.io/scrape?token=${TOKEN}`;const headers = {  "Cache-Control": "no-cache",  "Content-Type": "application/json"};const data = {  url: "https://example.com",  elements: [    { selector: "a" }  ],  addScriptTag: [{    content: "setTimeout(() => document.dispatchEvent(new CustomEvent('app:ready', { detail: { status: 'loaded' } })), 250);"  }],  waitForEvent: {    event: "app:ready",    timeout: 1000  }};const fetchContent = async () => {  const response = await fetch(url, {    method: 'POST',    headers: headers,    body: JSON.stringify(data)  });  const result = await response.json();  console.log(result);};fetchContent();
```

```
import requestsTOKEN = "YOUR_API_TOKEN_HERE"url = f"https://production-sfo.browserless.io/scrape?token={TOKEN}"headers = {    "Cache-Control": "no-cache",    "Content-Type": "application/json"}data = {    "url": "https://example.com",    "elements": [        { "selector": "a" }    ],    "addScriptTag": [{        "content": "setTimeout(() => document.dispatchEvent(new CustomEvent('app:ready', { detail: { status: 'loaded' } })), 250);"    }],    "waitForEvent": {        "event": "app:ready",        "timeout": 1000    }}response = requests.post(url, headers=headers, json=data)result = response.json()print(result)
```

```
import java.io.*;import java.net.URI;import java.net.http.*;public class FetchContentWithWaitForEvent {    public static void main(String[] args) {        String TOKEN = "YOUR_API_TOKEN_HERE";        String url = "https://production-sfo.browserless.io/scrape?token=" + TOKEN;        String jsonData = """        {            "url": "https://example.com",            "elements": [                { "selector": "a" }            ],            "addScriptTag": [{                "content": "setTimeout(() => document.dispatchEvent(new CustomEvent('app:ready', { detail: { status: 'loaded' } })), 250);"            }],            "waitForEvent": {                "event": "app:ready",                "timeout": 1000            }        }        """;        HttpClient client = HttpClient.newHttpClient();        HttpRequest request = HttpRequest.newBuilder()            .uri(URI.create(url))            .header("Cache-Control", "no-cache")            .header("Content-Type", "application/json")            .POST(HttpRequest.BodyPublishers.ofString(jsonData))            .build();        try {            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());            System.out.println("Response: " + response.body());        } catch (Exception e) {            e.printStackTrace();        }    }}
```

```
using System;using System.Net.Http;using System.Text;using System.Text.Json;using System.Threading.Tasks;class Program {    static async Task Main(string[] args) {        string TOKEN = "YOUR_API_TOKEN_HERE";        string url = $"https://production-sfo.browserless.io/scrape?token={TOKEN}";        string jsonData = @"        {            ""url"": ""https://example.com"",            ""elements"": [                { ""selector"": ""a"" }            ],            ""addScriptTag"": [{                ""content"": ""setTimeout(() => document.dispatchEvent(new CustomEvent('app:ready', { detail: { status: 'loaded' } })), 250);""            }],            ""waitForEvent"": {                ""event"": ""app:ready"",                ""timeout"": 1000            }        }";        using var client = new HttpClient();        var content = new StringContent(jsonData, Encoding.UTF8, "application/json");        try {            var response = await client.PostAsync(url, content);            response.EnsureSuccessStatusCode();            var result = await response.Content.ReadAsStringAsync();            Console.WriteLine("Response: " + result);        } catch (Exception ex) {            Console.WriteLine($"Error: {ex.Message}");        }    }}
```

warning

`waitForEvent` only works with custom events, not lifecycle events like `load` or `DOMContentLoaded`. Use [gotoOptions.waitUntil](https://docs.browserless.io/rest-apis/request-configuration#navigation-options) for lifecycle events.

## Configuration options​

The `/scrape` API supports shared [request configuration options](https://docs.browserless.io/rest-apis/request-configuration) that apply across REST endpoints. In addition to `elements` and selectors, you can:

- Control navigation with gotoOptions (for example waitUntil and timeout)
- Wait for conditions using waitForTimeout, waitForSelector, waitForFunction, and waitForEvent
- Reduce noise with rejectResourceTypes and rejectRequestPattern
- Continue on error with bestAttempt when async steps fail or time out