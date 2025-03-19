import os
import json
import requests
import re
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("Please set your GROQ_API_KEY environment variable.")

client = Groq(api_key=GROQ_API_KEY)

def generate_kyb_report(company_name, company_website):
    """
    Uses Groq API to generate a KYB report with improved prompt to handle missing data.
    """
    system_prompt = (
        "You are a seasoned business analyst with expertise in KYB due diligence. "
        "When given a company name and website, gather and summarize the following details: "
        "registration number, incorporation date, beneficial owners, key financial metrics, "
        "and any public risk indicators. Output ONLY a valid JSON object with keys: "
        "company_name, registration_number, incorporation_date, beneficial_owners, financial_summary, risk_indicators. "
        "If any data is missing, use 'Not publicly available' as the value. "
        "For financial_summary, include any available metrics like revenue, funding, valuation, etc. "
        "DO NOT include any explanatory text outside the JSON object. "
        "Ensure the response is properly formatted JSON that can be parsed by json.loads()."
    )
    
    user_prompt = (
        f"Company Name: {company_name}\nWebsite: {company_website}\n\n"
        f"Please research {company_name} and provide all available information in JSON format. "
        f"If specific data points are not publicly available, use 'Not publicly available' as the value, "
        f"but try to find as much information as possible from public sources."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        response = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            temperature=0.3,  # Lower temperature for more consistent output
            top_p=1,
            max_tokens=1024
        )
    except Exception as e:
        print(f"Error during Groq API call: {e}")
        return None
    
    output_text = response.choices[0].message.content
    
    # Extract JSON from the response if it's embedded in text
    json_match = re.search(r'```json\s*(.*?)\s*```', output_text, re.DOTALL)
    if json_match:
        output_text = json_match.group(1)
    else:
        # Try to find JSON object between curly braces
        json_match = re.search(r'({.*})', output_text, re.DOTALL)
        if json_match:
            output_text = json_match.group(1)
    
    try:
        kyb_report = json.loads(output_text)
        return kyb_report
    except json.JSONDecodeError:
        print("Failed to decode JSON from response. Creating structured report from raw output.")
        # Create a basic structured report with the raw output
        return {
            "company_name": company_name,
            "raw_data": output_text,
            "registration_number": "Not publicly available",
            "incorporation_date": "Not publicly available",
            "beneficial_owners": "Not publicly available",
            "financial_summary": {"details": "Not publicly available"},
            "risk_indicators": "Not publicly available"
        }

def scrape_additional_data(company_website):
    """
    Scrapes the company's public website to extract additional info for enrichment.
    Enhanced to extract more relevant information.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        res = requests.get(company_website, headers=headers, timeout=15)
        res.raise_for_status()
    except Exception as e:
        print(f"Error fetching {company_website}: {e}")
        return {"about_info": "Failed to retrieve website data"}
    
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # Try multiple selectors to find about information
    about_text = ""
    about_selectors = [
        soup.find(id=lambda x: x and ('about' in x.lower() if x else False)),
        soup.find("section", {"class": lambda x: x and ('about' in x.lower() if x else False)}),
        soup.find("div", {"class": lambda x: x and ('about' in x.lower() if x else False)}),
        soup.find(string=lambda text: text and 'About Us' in text)
    ]
    
    for selector in about_selectors:
        if selector:
            if hasattr(selector, 'get_text'):
                about_text = selector.get_text(separator=" ", strip=True)
                break
            else:
                # If it's a string, try to find its parent
                parent = selector.parent
                if parent:
                    about_text = parent.get_text(separator=" ", strip=True)
                    break
    
    # If no about section found, try to get meta description
    if not about_text:
        meta_desc = soup.find("meta", {"name": "description"})
        if meta_desc and meta_desc.get("content"):
            about_text = meta_desc.get("content")
    
    # Fallback: grab text from the body
    if not about_text:
        body_text = soup.get_text(separator=" ", strip=True)
        about_text = body_text[:500] + "..."
    
    # Try to find contact information
    contact_info = {}
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, res.text)
    if emails:
        contact_info["email"] = emails[0]  # Just take the first email
    
    # Try to find social media links
    social_media = {}
    social_platforms = ["linkedin", "twitter", "facebook", "instagram"]
    for platform in social_platforms:
        links = soup.find_all("a", href=lambda href: href and platform in href.lower())
        if links:
            social_media[platform] = links[0]["href"]
    
    return {
        "about_info": about_text[:500],  # Limit to 500 chars
        "contact_info": contact_info if contact_info else "Not found on website",
        "social_media": social_media if social_media else "Not found on website"
    }

def main():
    # Example company details
    company_name = "Brain Corp"
    company_website = "https://www.braincorp.com"
    
    print(f"Generating KYB report for {company_name}...")
    kyb_report = generate_kyb_report(company_name, company_website)
    
    if kyb_report:
        print("KYB Report from Groq API:")
        print(json.dumps(kyb_report, indent=2))
    else:
        print("KYB report generation failed.")
    
    print(f"\nScraping additional data from {company_website}...")
    enrichment_data = scrape_additional_data(company_website)
    
    if enrichment_data:
        print("Additional Data from Web Scraping:")
        print(json.dumps(enrichment_data, indent=2))
    else:
        print("No enrichment data found.")
    
    # Merge the two datasets for a complete KYB profile
    if kyb_report:
        full_profile = {**kyb_report, "web_data": enrichment_data}
        print("\nFinal Enriched KYB Profile:")
        print(json.dumps(full_profile, indent=2))
        
        # Save the report to a file
        with open(f"{company_name.replace(' ', '_')}_kyb_report.json", "w") as f:
            json.dump(full_profile, f, indent=2)
        print(f"\nReport saved to {company_name.replace(' ', '_')}_kyb_report.json")
    else:
        print("Unable to produce final KYB profile due to missing report.")

if __name__ == "__main__":
    main()