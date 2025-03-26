import os
import json
import requests
import re
from bs4 import BeautifulSoup
import streamlit as st
from groq import Groq
import pandas as pd

# Set page config
st.set_page_config(
    page_title="KYB Due Diligence Tool",
    page_icon="🔍",
    layout="wide"
)

# App title and description
st.title("Know Your Business (KYB) Due Diligence Tool")
st.markdown("""
This application helps you perform KYB due diligence by gathering information about a company
from various sources and presenting it in a structured format.
""")

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input("Enter your Groq API Key", type="password")
    company_name = st.text_input("Company Name", "Brain Corp")
    company_website = st.text_input("Company Website", "https://www.braincorp.com")
    
    run_button = st.button("Generate KYB Report", type="primary")
    
        # NEW: Prompt input field
    custom_prompt = st.text_area(
        "Special Instructions (Optional)", 
        help="Example: 'Only include companies with founder ownership' or 'Focus on European subsidiaries'"
    )

    # NEW: Edit mode toggle
    edit_mode = st.checkbox("Enable Edit Mode", help="Manually correct report data")

# Function definitions from script_v3.py
def generate_kyb_report(company_name, company_website, api_key, u_user_prompt=None):
    """Uses Groq API to generate a KYB report with enhanced prompt."""
    client = Groq(api_key=api_key)
    
    system_prompt = (
        "You are a seasoned business analyst with expertise in KYB due diligence. "
        "When given a company name and website, gather and summarize the following details: "
        "registration number, incorporation date, beneficial owners, key financial metrics, "
        "and any public risk indicators. Output ONLY a valid JSON object with keys: "
        "company_name, registration_number, incorporation_date, beneficial_owners, financial_summary, risk_indicators. "
        "For beneficial_owners, provide an array of objects with name and ownership_percentage when available. "
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
        with st.spinner("Generating KYB report via Groq API..."):
            response = client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                top_p=1,
                max_tokens=1024
            )
    except Exception as e:
        st.error(f"Error during Groq API call: {e}")
        return None
    
    output_text = response.choices[0].message.content
    
    # ADDED: Incorporate user prompt if provided

    if u_user_prompt:
        user_prompt += f"\n\nADDITIONAL REQUIREMENTS:\n{u_user_prompt}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}  # Changed from user_prompt to full_user_prompt
    ]
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
        st.warning("Failed to decode JSON from response. Creating structured report from raw output.")
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
    """Scrapes the company's public website for additional information."""
    try:
        with st.spinner(f"Scraping data from {company_website}..."):
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            res = requests.get(company_website, headers=headers, timeout=15)
            res.raise_for_status()
    except Exception as e:
        st.error(f"Error fetching {company_website}: {e}")
        return {"about_info": "Failed to retrieve website data"}
    
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # Initialize variables
    about_text = ""
    leadership_info = []
    contact_info = {}
    social_media = {}
    potential_risks = []
    
    # Try multiple selectors to find about information
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
    
    # Try to find leadership/team information
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
    """Simulates searching for news articles about the company to identify potential risks."""
    st.info(f"Searching for news about {company_name}... (placeholder functionality)")
    
    return {
        "news_search_performed": True,
        "note": "This is a placeholder for news risk analysis. In production, connect to a news API."
    }

# Main app logic
if run_button:
    if not api_key:
        st.error("Please enter your Groq API Key in the sidebar.")
    elif not company_name:
        st.error("Please enter a Company Name in the sidebar.")
    elif not company_website:
        st.error("Please enter a Company Website in the sidebar.")
    else:
        # Generate KYB report
        kyb_report = generate_kyb_report(company_name, company_website, api_key, custom_prompt)
        
        if not kyb_report:
            st.error("KYB report generation failed.")
        else:
            # Scrape additional data
            enrichment_data = scrape_additional_data(company_name, company_website)
            
            # Search for news
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
            
            # Display results in tabs
            tab1, tab2, tab3, tab4 = st.tabs(["Company Overview", "Beneficial Owners", "Risk Indicators", "Raw Data"])
            
            with tab1:
                st.header("Company Overview")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Basic Information")
                    st.write(f"**Company Name:** {full_profile.get('company_name', 'N/A')}")
                    st.write(f"**Registration Number:** {full_profile.get('registration_number', 'Not publicly available')}")
                    st.write(f"**Incorporation Date:** {full_profile.get('incorporation_date', 'Not publicly available')}")
                
                with col2:
                    st.subheader("Financial Summary")
                    financial_summary = full_profile.get('financial_summary', {})
                    if isinstance(financial_summary, dict) and financial_summary:
                        for key, value in financial_summary.items():
                            st.write(f"**{key.replace('_', ' ').title()}:** {value}")
                    else:
                        st.write("No financial information available")
                
                st.subheader("About")
                st.write(enrichment_data.get('about_info', 'No information available'))
                
                st.subheader("Contact Information")
                contact_info = enrichment_data.get('contact_info', {})
                if isinstance(contact_info, dict) and contact_info:
                    for key, value in contact_info.items():
                        st.write(f"**{key.title()}:** {value}")
                else:
                    st.write("No contact information available")
                
                st.subheader("Social Media")
                social_media = enrichment_data.get('social_media', {})
                if isinstance(social_media, dict) and social_media:
                    for platform, url in social_media.items():
                        st.write(f"**{platform.title()}:** [{url}]({url})")
                else:
                    st.write("No social media information available")
            
            with tab2:
                st.header("Beneficial Owners")
                beneficial_owners = full_profile.get('beneficial_owners', [])
                
                if beneficial_owners and isinstance(beneficial_owners, list):
                    # Convert to DataFrame for better display
                    owners_data = []
                    for owner in beneficial_owners:
                        if isinstance(owner, dict):
                            owners_data.append({
                                "Name": owner.get("name", "N/A"),
                                "Ownership %": owner.get("ownership_percentage", "Unknown"),
                                "Title": owner.get("title", "N/A")
                            })
                    
                    if owners_data:
                        st.dataframe(pd.DataFrame(owners_data), use_container_width=True)
                    else:
                        st.write("No beneficial owners information available")
                else:
                    st.write("No beneficial owners information available")
            
            with tab3:
                st.header("Risk Indicators")
                risk_indicators = full_profile.get('risk_indicators', [])
                
                if risk_indicators and isinstance(risk_indicators, list):
                    for i, risk in enumerate(risk_indicators):
                        st.write(f"{i+1}. {risk}")
                else:
                    st.write("No risk indicators identified")
            
            with tab4:
                st.header("Raw Data")
                st.json(full_profile)
                
                # Option to download the report
                report_json = json.dumps(full_profile, indent=2)
                st.download_button(
                    label="Download Full Report (JSON)",
                    data=report_json,
                    file_name=f"{company_name.replace(' ', '_')}_kyb_report.json",
                    mime="application/json"
                )
else:
    st.info("Enter your Groq API key, company name, and website in the sidebar, then click 'Generate KYB Report'.")
    
    # Show example report structure
    with st.expander("Example Report Structure"):
        st.code("""
{
  "company_name": "Example Corp",
  "registration_number": "12345678",
  "incorporation_date": "2010-01-15",
  "beneficial_owners": [
    {"name": "Jane Doe", "ownership_percentage": "51%"},
    {"name": "John Smith", "ownership_percentage": "49%"}
  ],
  "financial_summary": {
    "revenue": "$10M (2022)",
    "funding": "Series B, $25M (2021)"
  },
  "risk_indicators": [
    "Regulatory investigation in 2021",
    "Lawsuit from competitor in 2022"
  ],
  "web_data": {
    "about_info": "Company description...",
    "leadership_info": [...],
    "contact_info": {...},
    "social_media": {...},
    "potential_risks": [...]
  },
  "news_data": {...}
}
        """, language="json")