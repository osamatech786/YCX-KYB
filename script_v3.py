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
    Uses Groq API to generate a KYB report with enhanced prompt for better extraction
    of beneficial owners and risk indicators.
    """
    system_prompt = (
        "You are a seasoned business analyst with expertise in KYB due diligence. "
        "When given a company name and website, gather and summarize the following details: "
        "registration number, incorporation date, beneficial owners, key financial metrics, "
        "and any public risk indicators. Output ONLY a valid JSON object with keys: "
        "company_name, registration_number, incorporation_date, beneficial_owners, financial_summary, risk_indicators. "
        "For beneficial_owners, provide an array of objects with name and ownership_percentage when available. "
        "For risk_indicators, provide an array of specific risk factors identified. "
        "If any data is missing, use 'Not publicly available' as the value. "
        "For financial_summary, include any available metrics like revenue, funding, valuation, etc. "
        "DO NOT include any explanatory text outside the JSON object. "
        "Ensure the response is properly formatted JSON that can be parsed by json.loads()."
    )
    
    user_prompt = (
        f"Company Name: {company_name}\nWebsite: {company_website}\n\n"
        f"Please research {company_name} and provide all available information in JSON format. "
        f"Pay special attention to beneficial owners (with their ownership percentages if available) "
        f"and any risk indicators such as regulatory issues, legal disputes, negative news, "
        f"or financial concerns. If specific data points are not publicly available, "
        f"use 'Not publicly available' as the value, but try to find as much information "
        f"as possible from public sources."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        response = client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            temperature=0.3,
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
        
        # Ensure beneficial_owners is an array if it's a string
        if isinstance(kyb_report.get('beneficial_owners'), str):
            if kyb_report['beneficial_owners'] == "Not publicly available":
                kyb_report['beneficial_owners'] = []
            else:
                # Try to parse from string to array
                kyb_report['beneficial_owners'] = [{"name": kyb_report['beneficial_owners'], "ownership_percentage": "Unknown"}]
        
        # Ensure risk_indicators is an array if it's a string
        if isinstance(kyb_report.get('risk_indicators'), str):
            if kyb_report['risk_indicators'] == "Not publicly available":
                kyb_report['risk_indicators'] = []
            else:
                # Split by commas or convert to single item array
                kyb_report['risk_indicators'] = [item.strip() for item in kyb_report['risk_indicators'].split(',')]
        
        return kyb_report
    except json.JSONDecodeError:
        print("Failed to decode JSON from response. Creating structured report from raw output.")
        # Create a basic structured report with the raw output
        return {
            "company_name": company_name,
            "raw_data": output_text,
            "registration_number": "Not publicly available",
            "incorporation_date": "Not publicly available",
            "beneficial_owners": [],
            "financial_summary": {"details": "Not publicly available"},
            "risk_indicators": []
        }

def scrape_additional_data(company_name, company_website):
    """
    Scrapes the company's public website and searches for additional risk indicators
    and beneficial ownership information.
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
    
    # Initialize variables before using them
    leadership_info = []
    contact_info = {}
    
    # Try to find leadership/team information (potential beneficial owners)
    team_selectors = [
        soup.find(id=lambda x: x and any(term in x.lower() for term in ['team', 'leadership', 'management', 'founders']) if x else False),
        soup.find("section", {"class": lambda x: x and any(term in x.lower() for term in ['team', 'leadership', 'management', 'founders']) if x else False}),
        soup.find("div", {"class": lambda x: x and any(term in x.lower() for term in ['team', 'leadership', 'management', 'founders']) if x else False})
    ]
    
    for selector in team_selectors:
        if selector:
            # Look for names and titles
            people = selector.find_all(['h2', 'h3', 'h4', 'strong'])
            for person in people[:5]:  # Limit to first 5 to avoid too much noise
                name = person.get_text(strip=True)
                if len(name.split()) >= 2:  # Simple check if it looks like a name
                    title = ""
                    next_elem = person.find_next(['p', 'span', 'div'])
                    if next_elem:
                        title = next_elem.get_text(strip=True)
                    leadership_info.append({"name": name, "title": title})
    
    # Try to find contact information
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
    
    # Look for potential risk indicators in the page text
    risk_keywords = [
        "litigation", "lawsuit", "legal action", "investigation", "regulatory", 
        "compliance", "penalty", "fine", "settlement", "data breach", "security incident",
        "controversy", "scandal", "bankruptcy", "restructuring", "layoffs"
    ]
    
    potential_risks = []
    page_text = soup.get_text(separator=" ", strip=True).lower()
    
    for keyword in risk_keywords:
        if keyword in page_text:
            # Find the context around the keyword
            start = max(0, page_text.find(keyword) - 50)
            end = min(len(page_text), page_text.find(keyword) + len(keyword) + 50)
            context = page_text[start:end]
            potential_risks.append(f"Potential {keyword} mention: '{context}'")
    
    return {
        "about_info": about_text[:500],  # Limit to 500 chars
        "leadership_info": leadership_info if leadership_info else "Not found on website",
        "contact_info": contact_info if contact_info else "Not found on website",
        "social_media": social_media if social_media else "Not found on website",
        "potential_risks": potential_risks if potential_risks else "None detected on website"
    }

def search_news_for_risks(company_name):
    """
    Simulates searching for news articles about the company to identify potential risks.
    In a production environment, this would connect to a news API or use web scraping.
    """
    # This is a placeholder. In a real implementation, you would:
    # 1. Connect to a news API (like NewsAPI, GDELT, etc.)
    # 2. Search for recent articles mentioning the company
    # 3. Analyze sentiment and extract risk-related information
    
    print(f"Searching for news about {company_name}...")
    
    # Placeholder return
    return {
        "news_search_performed": True,
        "note": "This is a placeholder for news risk analysis. In production, connect to a news API."
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
        return
    
    print(f"\nScraping additional data from {company_website}...")
    enrichment_data = scrape_additional_data(company_name, company_website)
    
    if enrichment_data:
        print("Additional Data from Web Scraping:")
        print(json.dumps(enrichment_data, indent=2))
    else:
        print("No enrichment data found.")
    
    # Optional: Search for news about the company
    news_data = search_news_for_risks(company_name)
    
    # Merge the datasets for a complete KYB profile
    full_profile = {**kyb_report, "web_data": enrichment_data, "news_data": news_data}
    
    # Enhance beneficial owners with leadership info if beneficial owners is empty
    if not kyb_report.get('beneficial_owners') or len(kyb_report.get('beneficial_owners', [])) == 0:
        if enrichment_data.get('leadership_info') and enrichment_data['leadership_info'] != "Not found on website":
            full_profile['beneficial_owners'] = [
                {"name": leader["name"], "ownership_percentage": "Unknown", "title": leader["title"]}
                for leader in enrichment_data['leadership_info']
            ]
    
    # Enhance risk indicators with potential risks from website
    if enrichment_data.get('potential_risks') and enrichment_data['potential_risks'] != "None detected on website":
        if not full_profile.get('risk_indicators') or len(full_profile.get('risk_indicators', [])) == 0:
            full_profile['risk_indicators'] = enrichment_data['potential_risks']
        else:
            full_profile['risk_indicators'].extend(enrichment_data['potential_risks'])
    
    print("\nFinal Enriched KYB Profile:")
    print(json.dumps(full_profile, indent=2))
    
    # Save the report to a file
    with open(f"{company_name.replace(' ', '_')}_kyb_report.json", "w") as f:
        json.dump(full_profile, f, indent=2)
    print(f"\nReport saved to {company_name.replace(' ', '_')}_kyb_report.json")

if __name__ == "__main__":
    main()

