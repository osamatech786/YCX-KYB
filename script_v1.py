import os
import json
import requests
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv

load_dotenv()  # This will load the variables from .env file

# It's recommended to use a .env file for storing sensitive information like API keys

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("Please set your GROQ_API_KEY environment variable.")

# Initialize the Groq API client
client = Groq(api_key=GROQ_API_KEY)

# --- PART A: Advanced Prompt Engineering for KYB ---
def generate_kyb_report(company_name, company_website):
    """
    Uses Groq API to generate a KYB report by instructing the LLM with an advanced prompt.
    """
    # Construct the system prompt instructing the LLM on the KYB task
    system_prompt = (
        "You are a seasoned business analyst with expertise in KYB due diligence. "
        "When given a company name and website, gather and summarize the following details: "
        "registration number, incorporation date, beneficial owners, key financial metrics, "
        "and any public risk indicators. Output the data as a JSON object with keys: "
        "company_name, registration_number, incorporation_date, beneficial_owners, financial_summary, risk_indicators. "
        "If any data is missing, use 'N/A'."
    )
    # Combine the system prompt with a user message containing the company details
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Company Name: {company_name}\nWebsite: {company_website}"}
    ]
    # Call the Groq Chat Completion API
    try:
        response = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",  # choose a model that fits your context length and quality needs
            temperature=0.7,
            top_p=1,
            max_tokens=512
        )
    except Exception as e:
        print(f"Error during Groq API call: {e}")
        return None
    # Extract the output from the response
    output_text = response.choices[0].message.content
    try:
        kyb_report = json.loads(output_text)
    except json.JSONDecodeError:
        print("Failed to decode JSON from response:")
        print(output_text)
        return None
    return kyb_report
    
    
# --- PART B: Data Scraping for Enrichment ---
def scrape_additional_data(company_website):
    """
    Scrapes the company's public website to extract additional info for enrichment.
    For example, it attempts to extract the 'About Us' text.
    """
    try:
        res = requests.get(company_website, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"Error fetching {company_website}: {e}")
        return {}
    soup = BeautifulSoup(res.text, 'html.parser')
    # Attempt to extract text from a common section, e.g., an element with id 'about' or a <section>
    about_text = ""
    about_section = soup.find(id="about") or soup.find("section", {"class": "about"})
    if about_section:
        about_text = about_section.get_text(separator=" ", strip=True)
    else:
        # Fallback: grab the first 300 characters from the body text
        body_text = soup.get_text(separator=" ", strip=True)
        about_text = body_text[:300] + "..."
    return {"about_info": about_text}


# --- PART C: Main Workflow ---
def main():
    # Example company details; replace these with your target KYB entity

    # company_name = "Acme Corporation"
    # company_website = "https://www.acme-corp.com"

    # company_name = "Anthropic PBC"
    # company_website = "https://www.anthropic.com/"
    
    company_name = "Brain Corp"
    company_website = "https://www.braincorp.com"

    print("Generating KYB report via Groq API...")
    kyb_report = generate_kyb_report(company_name, company_website)
    if kyb_report:
        print("KYB Report from Groq API:")
        print(json.dumps(kyb_report, indent=2))
    else:
        print("KYB report generation failed.")
    print("\nScraping additional data from company website...")
    enrichment_data = scrape_additional_data(company_website)
    if enrichment_data:
        print("Additional Data from Web Scraping:")
        print(json.dumps(enrichment_data, indent=2))
    else:
        print("No enrichment data found.")
    # Merge the two datasets for a complete KYB profile
    if kyb_report:
        full_profile = {**kyb_report, **enrichment_data}
        print("\nFinal Enriched KYB Profile:")
        print(json.dumps(full_profile, indent=2))
    else:
        print("Unable to produce final KYB profile due to missing report.")
if __name__ == "__main__":
    main()