import os
import json
import requests
import re
import time
from bs4 import BeautifulSoup
import streamlit as st
from groq import Groq
import pandas as pd
from datetime import datetime

# Set page config
st.set_page_config(
    page_title="KYB Due Diligence Tool",
    page_icon="🔍",
    layout="wide"
)

# App title and description
st.title("Know Your Business (KYB) Due Diligence Tool")
st.markdown("""
This application helps you perform KYB due diligence by gathering information about companies
from various sources and presenting it in a structured format.
""")

# Function definitions
def generate_kyb_report(company_name, company_website, api_key):
    """Uses Groq API to generate a KYB report with enhanced prompt."""
    client = Groq(api_key=api_key)
    
    system_prompt = """You are a seasoned business analyst. When given a company name and website, 
    gather and summarize the following details in a structured JSON format:
    {
        "company_name": "Company name",
        "industry": "Company's industry",
        "headquarters": "Company HQ location",
        "founding_year": "Year founded",
        "employees": "Number of employees",
        "funding": "Total funding raised",
        "revenue": "Annual revenue",
        "valuation": "Company valuation",
        "founders": "Founders names and LinkedIn URLs",
        "key_contacts": "Key executive contacts",
        "ai_models": "AI models used",
        "ai_use_case": "Primary AI use cases",
        "ai_frameworks": "AI frameworks used",
        "ai_products": "AI products/services offered",
        "patents": "Patent details",
        "research_papers": "Published research papers",
        "partnerships": "Key partnerships",
        "tech_stack": "Technology stack",
        "customers": "Notable customers",
        "case_studies": "Case studies",
        "awards": "Awards and recognition",
        "compliance": "Compliance and regulatory adherence",
        "market_presence": "Market presence",
        "community": "Community engagement",
        "ethics": "AI ethics policies",
        "competitors": "Competitor analysis",
        "media": "Recent media mentions"
    }
    Use 'Not publicly available' for missing data."""
    
    user_prompt = (
        f"Company Name: {company_name}\nWebsite: {company_website}\n\n"
        f"Please research {company_name} and provide all available information in JSON format."
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
        output_text = response.choices[0].message.content
        json_match = re.search(r'```json\s*(.*?)\s*```', output_text, re.DOTALL) or re.search(r'({.*})', output_text, re.DOTALL)
        report = json.loads(json_match.group(1) if json_match else output_text)
        # Ensure company_name is included
        report['company_name'] = company_name
        return report
    except Exception as e:
        st.error(f"Error during Groq API call: {e}")
        return {"company_name": company_name, "error": str(e)}

def scrape_additional_data(company_name, company_website):
    """Scrapes the company's public website for additional information."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
        res = requests.get(company_website, headers=headers, timeout=15)
        res.raise_for_status()
    except Exception as e:
        return {"about_info": f"Failed to retrieve website data: {e}"}
    
    soup = BeautifulSoup(res.text, 'html.parser')
    about_text = ""
    for selector in [
        soup.find(id=lambda x: x and 'about' in x.lower()),
        soup.find("section", {"class": lambda x: x and 'about' in x.lower()}),
        soup.find("div", {"class": lambda x: x and 'about' in x.lower()}),
        soup.find(string=lambda text: text and 'About Us' in text)
    ]:
        if selector and hasattr(selector, 'get_text'):
            about_text = selector.get_text(separator=" ", strip=True)
            break
        elif selector and selector.parent:
            about_text = selector.parent.get_text(separator=" ", strip=True)
            break
    
    if not about_text:
        meta_desc = soup.find("meta", {"name": "description"})
        about_text = meta_desc.get("content") if meta_desc else soup.get_text(separator=" ", strip=True)[:500] + "..."
    
    return {"about_info": about_text[:500] + "..." if len(about_text) > 500 else about_text}

def search_duckduckgo(query, max_results=5):
    """Search DuckDuckGo without an API key, prioritizing official websites."""
    url = "https://duckduckgo.com/html/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
    params = {"q": query}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        for link in soup.find_all('a', class_='result__url', href=True):
            href = link['href']
            if href.startswith('/l/?uddg='):
                actual_url = re.search(r'https?://[^&]+', href)
                if actual_url:
                    url = actual_url.group(0)
                    if re.search(r'(www\.)?' + re.escape(query.split()[0].lower()) + r'\.(com|org|co)', url):
                        results.append(url)
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        st.error(f"DuckDuckGo search failed: {e}")
        return []

def find_company_website(company_name):
    """Search for company's official website using DuckDuckGo."""
    query = f"{company_name} official website"
    results = search_duckduckgo(query, max_results=1)
    return results[0] if results else None

def process_and_update_database(company_name, company_website, kyb_report, enrichment_data, core_df):
    """Update user_output.csv with new company data, keeping core dataset unchanged."""
    columns = [
        'Company Name', 'Website', 'Industry', 'Headquarters', 'Founding Year', 'No.Employees',
        'Funding Raised', 'Revenue', 'Company Valuation', 'Founders', 'Key Contacts',
        'AI Model Used', 'Primary AI Use Case', 'AI Frameworks Used', 'AI Products/Services Offered',
        'Patent Details', 'AI Research Papers Published', 'Partnerships', 'Tech Stack',
        'Customer Base', 'Case Studies', 'Awards', 'Compliance and Regulatory Adherence',
        'Market Presence', 'Community Engagement', 'AI Ethics Policies', 'Competitor Analysis',
        'Recent Media Mentions', 'Company Description'
    ]
    
    # Load or initialize user_output.csv
    output_file = "user_output.csv"
    if os.path.exists(output_file):
        user_df = pd.read_csv(output_file)
    else:
        user_df = pd.DataFrame(columns=columns)
    
    # Flatten lists and dicts to strings
    def flatten(value):
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        elif isinstance(value, dict):
            return ", ".join(f"{k}: {v}" for k, v in value.items())
        return str(value)
    
    new_data = {
        'Company Name': company_name,
        'Website': company_website,
        'Industry': flatten(kyb_report.get('industry', 'Not publicly available')),
        'Headquarters': flatten(kyb_report.get('headquarters', 'Not publicly available')),
        'Founding Year': flatten(kyb_report.get('founding_year', 'Not publicly available')),
        'No.Employees': flatten(kyb_report.get('employees', 'Not publicly available')),
        'Funding Raised': flatten(kyb_report.get('funding', 'Not publicly available')),
        'Revenue': flatten(kyb_report.get('revenue', 'Not publicly available')),
        'Company Valuation': flatten(kyb_report.get('valuation', 'Not publicly available')),
        'Founders': flatten(kyb_report.get('founders', 'Not publicly available')),
        'Key Contacts': flatten(kyb_report.get('key_contacts', 'Not publicly available')),
        'AI Model Used': flatten(kyb_report.get('ai_models', 'Not publicly available')),
        'Primary AI Use Case': flatten(kyb_report.get('ai_use_case', 'Not publicly available')),
        'AI Frameworks Used': flatten(kyb_report.get('ai_frameworks', 'Not publicly available')),
        'AI Products/Services Offered': flatten(kyb_report.get('ai_products', 'Not publicly available')),
        'Patent Details': flatten(kyb_report.get('patents', 'Not publicly available')),
        'AI Research Papers Published': flatten(kyb_report.get('research_papers', 'Not publicly available')),
        'Partnerships': flatten(kyb_report.get('partnerships', 'Not publicly available')),
        'Tech Stack': flatten(kyb_report.get('tech_stack', 'Not publicly available')),
        'Customer Base': flatten(kyb_report.get('customers', 'Not publicly available')),
        'Case Studies': flatten(kyb_report.get('case_studies', 'Not publicly available')),
        'Awards': flatten(kyb_report.get('awards', 'Not publicly available')),
        'Compliance and Regulatory Adherence': flatten(kyb_report.get('compliance', 'Not publicly available')),
        'Market Presence': flatten(kyb_report.get('market_presence', 'Not publicly available')),
        'Community Engagement': flatten(kyb_report.get('community', 'Not publicly available')),
        'AI Ethics Policies': flatten(kyb_report.get('ethics', 'Not publicly available')),
        'Competitor Analysis': flatten(kyb_report.get('competitors', 'Not publicly available')),
        'Recent Media Mentions': flatten(kyb_report.get('media', 'Not publicly available')),
        'Company Description': flatten(enrichment_data.get('about_info', 'Not publicly available'))
    }
    
    # Update or append to user_df
    if company_name.lower() in user_df['Company Name'].str.lower().values:
        idx = user_df[user_df['Company Name'].str.lower() == company_name.lower()].index[0]
        user_df.loc[idx] = new_data
    else:
        user_df = pd.concat([user_df, pd.DataFrame([new_data])], ignore_index=True)
    
    user_df.to_csv(output_file, index=False)

def display_report(kyb_report, enrichment_data):
    """Display the KYB report in a user-friendly format with tabs."""
    company_name = kyb_report.get('company_name', 'Unknown')
    st.header(f"KYB Report for {company_name}")
    
    tab1, tab2, tab3 = st.tabs(["Company Overview", "AI Capabilities", "Business Details"])
    
    with tab1:
        st.subheader("Basic Information")
        cols = st.columns(2)
        with cols[0]:
            st.write(f"**Company Name:** {company_name}")
            st.write(f"**Website:** {kyb_report.get('website', 'Not provided')}")
            st.write(f"**Industry:** {kyb_report.get('industry', 'Not publicly available')}")
            st.write(f"**Headquarters:** {kyb_report.get('headquarters', 'Not publicly available')}")
        with cols[1]:
            st.write(f"**Founded:** {kyb_report.get('founding_year', 'Not publicly available')}")
            st.write(f"**Employees:** {kyb_report.get('employees', 'Not publicly available')}")
            st.write(f"**Funding:** {kyb_report.get('funding', 'Not publicly available')}")
            st.write(f"**Revenue:** {kyb_report.get('revenue', 'Not publicly available')}")
        
        st.subheader("Company Description")
        st.write(enrichment_data.get('about_info', 'Not publicly available'))
    
    with tab2:
        st.subheader("AI Technology")
        st.write(f"**AI Models:** {', '.join(kyb_report.get('ai_models', ['Not publicly available']))}")
        st.write(f"**Primary Use Case:** {', '.join(kyb_report.get('ai_use_case', ['Not publicly available']))}")
        st.write(f"**Frameworks:** {', '.join(kyb_report.get('ai_frameworks', ['Not publicly available']))}")
        st.write(f"**Products/Services:** {', '.join(kyb_report.get('ai_products', ['Not publicly available']))}")
        
        st.subheader("Research & Development")
        st.write(f"**Patents:** {kyb_report.get('patents', 'Not publicly available')}")
        st.write(f"**Research Papers:** {', '.join(kyb_report.get('research_papers', ['Not publicly available']))}")
    
    with tab3:
        st.subheader("Business Information")
        st.write(f"**Partnerships:** {', '.join(kyb_report.get('partnerships', ['Not publicly available']))}")
        st.write(f"**Customers:** {', '.join(kyb_report.get('customers', ['Not publicly available']))}")
        st.write(f"**Case Studies:** {kyb_report.get('case_studies', 'Not publicly available')}")
        st.write(f"**Market Presence:** {', '.join(kyb_report.get('market_presence', ['Not publicly available']))}")
        
        st.subheader("Compliance & Ethics")
        st.write(f"**Regulatory Compliance:** {', '.join(kyb_report.get('compliance', ['Not publicly available']))}")
        st.write(f"**AI Ethics:** {', '.join(kyb_report.get('ethics', ['Not publicly available']))}")
    
    # Download button
    full_data = {**kyb_report, "web_data": enrichment_data}
    st.download_button(
        label="Download Report (JSON)",
        data=json.dumps(full_data, indent=2),
        file_name=f"{company_name.replace(' ', '_')}_kyb_report.json",
        mime="application/json"
    )

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input("Enter your Groq API Key", type="password")
    company_name = st.text_input("Company Name")
    run_button = st.button("Generate KYB Report", type="primary")

# Main app logic
if run_button:
    if not api_key:
        st.error("Please enter your Groq API Key.")
    elif not company_name:
        st.error("Please enter a Company Name.")
    else:
        try:
            core_df = pd.read_csv("knowYourAi - Company Details.csv")
            company_data = core_df[core_df['Company Name'].str.lower() == company_name.lower()]
            
            if not company_data.empty:
                st.success(f"Found existing data for {company_name}")
                company_website = company_data.iloc[0]['Website'].split(' [')[0]
            else:
                st.info(f"Adding new company: {company_name}")
                company_website = find_company_website(company_name)
                if not company_website:
                    st.error("Could not find company website. Please try again.")
                    st.stop()
                st.success(f"Found company website: {company_website}")

            with st.spinner(f"Processing {company_name}..."):
                kyb_report = generate_kyb_report(company_name, company_website, api_key)
                if not kyb_report or "error" in kyb_report:
                    st.error("KYB report generation failed.")
                else:
                    enrichment_data = scrape_additional_data(company_name, company_website)
                    process_and_update_database(company_name, company_website, kyb_report, enrichment_data, core_df)
                    display_report(kyb_report, enrichment_data)

        except Exception as e:
            st.error(f"Error processing request: {e}")

else:
    st.info("Enter your Groq API key and company name, then click 'Generate KYB Report'.")