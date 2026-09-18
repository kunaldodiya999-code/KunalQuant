import requests

CLIENT_ID = "1101414659"
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJ1c2VyUmVnaW9uIjoiUjEiLCJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzg5ODEwMDM5LCJpYXQiOjE3ODk3MjM2MzksInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTAxNDE0NjU5In0.oD3ZN72DaWte_YVPNqnS2XpGMXjoNYhlbgtqnwT9CrQhTc8UJ_bR93eXO1iQJwS8FfTN0QCAX2zxmU2VBJkjFg"

url = "https://api.dhan.co/v2/profile"

headers = {
    "access-token": ACCESS_TOKEN
}

response = requests.get(url, headers=headers)

print("HTTP Status:", response.status_code)
print("Response:")
print(response.text)