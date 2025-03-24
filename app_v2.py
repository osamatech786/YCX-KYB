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
        return json.loads(json_match.group(1) if json_match else output_text)
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
    """Search DuckDuckGo without an API key."""
    url = "https://duckduckgo.com/html/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
    params = {"q": query}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        for link in soup.find_all('a', class_='result__url', href=True)[:max_results]:
            href = link['href']
            if href.startswith('/l/?uddg='):
                # Extract the actual URL from DuckDuckGo's redirect
                actual_url = re.search(r'https?://[^\&]+', href)
                if actual_url:
                    results.append(actual_url.group(0))
            else:
                results.append(href)
        return results
    except Exception as e:
        st.error(f"DuckDuckGo search failed: {e}")
        return []

def find_company_website(company_name):
    """Search for company's official website using DuckDuckGo."""
    query = f"{company_name} official website"
    results = search_duckduckgo(query, max_results=1)
    return results[0] if results else None

def process_company(company_name, company_website, api_key):
    """Process a single company and return the full KYB profile."""
    kyb_report = generate_kyb_report(company_name, company_website, api_key)
    if not kyb_report or "error" in kyb_report:
        return {"company_name": company_name, "error": "KYB report generation failed"}
    
    enrichment_data = scrape_additional_data(company_name, company_website)
    return {**kyb_report, "web_data": enrichment_data}

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input("Enter your Groq API Key", type="password")
    input_method = st.radio("Choose input method:", ["Single Company", "Batch Processing (CSV)"])
    
    if input_method == "Single Company":
        company_name = st.text_input("Company Name", "Brain Corp")
        company_website = st.text_input("Company Website", "https://www.braincorp.com")
        run_button = st.button("Generate KYB Report", type="primary")
    else:
        st.write("Upload a CSV with 'Company Name' and optional 'Website'")
        uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
        if uploaded_file:
            csv_data = pd.read_csv(uploaded_file)
            st.write("Preview of uploaded data:")
            st.dataframe(csv_data.head())
            if 'Company Name' not in csv_data.columns:
                st.error("CSV must contain 'Company Name' column")
                run_batch = False
            else:
                num_companies = st.slider("Number of companies to process", 1, len(csv_data), min(5, len(csv_data)))
                run_batch = st.button("Process Companies", type="primary")
        else:
            run_batch = False

# Main app logic
if input_method == "Single Company" and run_button:
    if not api_key:
        st.error("Please enter your Groq API Key.")
    elif not company_name:
        st.error("Please enter a Company Name.")
    else:
        with st.spinner(f"Processing {company_name}..."):
            if not company_website:
                company_website = find_company_website(company_name) or "https://example.com"
            full_profile = process_company(company_name, company_website, api_key)
            if "error" in full_profile:
                st.error(full_profile["error"])
            else:
                st.subheader("KYB Report")
                st.json(full_profile)
                st.download_button(
                    label="Download Report (JSON)",
                    data=json.dumps(full_profile, indent=2),
                    file_name=f"{company_name.replace(' ', '_')}_kyb_report.json",
                    mime="application/json"
                )

elif input_method == "Batch Processing (CSV)" and run_batch:
    if not api_key:
        st.error("Please enter your Groq API Key.")
    else:
        progress_bar = st.progress(0)
        results = []
        for i, row in csv_data.head(num_companies).iterrows():
            company_name = row["Company Name"]
            company_website = row.get("Website") or find_company_website(company_name) or "https://example.com"
            result = process_company(company_name, company_website, api_key)
            results.append(result)
            progress_bar.progress((i + 1) / num_companies)
            time.sleep(1)  # Avoid rate limits
        
        st.subheader("Batch Results")
        st.json(results)
        st.download_button(
            label="Download Full Results (JSON)",
            data=json.dumps(results, indent=2),
            file_name="kyb_batch_results.json",
            mime="application/json"
        )

else:
    st.info("Enter your Groq API key and company details, then click 'Generate KYB Report' or upload a CSV.")