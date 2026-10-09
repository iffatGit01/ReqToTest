import re
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "https://lms.bjitgroup.com/"

@pytest.fixture
def page():
    page = Page()
    yield page
    page.close()

def test_tc001_login_succeeds_with_valid_credentials(page):
    """
    Steps:
    1. Open the login page
    2. Enter jane@example.com and Passw0rd!
    3. Click Sign in
    """
    page.goto(BASE_URL)
    expect(page).to_have_url(BASE_URL)
    username_input = page.locator("#username")
    username_input.fill("jane@example.com")
    password_input = page.locator("#password")
    password_input.fill("Passw0rd!")
    sign_in_button = page.locator("#submit")
    sign_in_button.click()
    expect(page).to_have_text("Welcome, Jane")

def test_tc002_login_rejected_when_password_is_empty(page):
    """
    Steps:
    1. Open the login page
    2. Enter jane@example.com
    3. Leave password empty
    4. Click Sign in
    """
    page.goto(BASE_URL)
    expect(page).to_have_url(BASE_URL)
    username_input = page.locator("#username")
    username_input.fill("jane@example.com")
    password_input = page.locator("#password")
    password_input.fill("")
    sign_in_button = page.locator("#submit")
    sign_in_button.click()
    expect(page).to_have_text("Password is required")

def test_tc003_login_succeeds_with_valid_credentials_and_multiple_attempts(page):
    """
    Steps:
    1. Open the login page
    2. Enter jane@example.com and Passw0rd!
    3. Click Sign in
    4. Enter invalid email and password
    5. Click Sign in
    6. Enter invalid email and password
    7. Click Sign in
    8. Enter invalid email and password
    9. Click Sign in
    10. Enter invalid email and password
    11. Click Sign in
    12. Enter valid email and password
    13. Click Sign in
    """
    page.goto(BASE_URL)
    expect(page).to_have_url(BASE_URL)
    username_input = page.locator("#username")
    username_input.fill("jane@example.com")
    password_input = page.locator("#password")
    password_input.fill("Passw0rd!")
    sign_in_button = page.locator("#submit")
    sign_in_button.click()
    expect(page).to_have_text("Welcome, Jane")
    username_input.fill("invalid@example.com")
    password_input.fill("invalid")
    sign_in_button.click()
    expect(page).to_have_text("Invalid email or password")
    username_input.fill("invalid@example.com")
    password_input.fill("invalid")
    sign_in_button.click()
    expect(page).to_have_text("Invalid email or password")
    username_input.fill("invalid@example.com")
    password_input.fill("invalid")
    sign_in_button.click()
    expect(page).to_have_text("Invalid email or password")
    username_input.fill("invalid@example.com")
    password_input.fill("invalid")
    sign_in_button.click()
    username_input.fill("jane@example.com")
    password_input.fill("Passw0rd!")
    sign_in_button.click()
    expect(page).to_have_text("Welcome, Jane")
