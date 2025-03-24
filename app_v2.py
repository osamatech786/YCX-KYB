import os
import json
import requests
import re
import time
from bs4 import BeautifulSoup
import streamlit as st
from groq import Groq
import pandas as pd
from io import StringIO
from datetime import datetime
import googlesearch  # You'll need to add this to requirements.txt

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
    """
    
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
        st.error(f"Error during Groq API call: {e}")
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
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        res = requests.get(company_website, headers=headers, timeout=15)
        res.raise_for_status()
    except Exception as e:
        return {"about_info": f"Failed to retrieve website data: {e}"}
    
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
        "litigation", "lawsuit", "fine", "penalty", "investigation", "regulatory action",
        "compliance issue", "data breach", "security incident", "fraud", "misconduct",
        "violation", "sanction", "warning", "cease and desist", "settlement"
    ]
    
    page_text = soup.get_text(separator=" ", strip=True).lower()
    for keyword in risk_keywords:
        if keyword in page_text:
            # Try to get some context around the keyword
            keyword_index = page_text.find(keyword)
            start_index = max(0, keyword_index - 50)
            end_index = min(len(page_text), keyword_index + len(keyword) + 50)
            context = page_text[start_index:end_index]
            potential_risks.append(f"Website mentions '{keyword}': ...{context}...")
    
    return {
        "about_info": about_text[:500] + "..." if len(about_text) > 500 else about_text,
        "leadership_info": leadership_info,
        "contact_info": contact_info,
        "social_media": social_media,
        "potential_risks": potential_risks if potential_risks else "None detected on website"
    }

def search_news_for_risks(company_name):
    """Simulates searching for news articles about the company to identify potential risks."""
    return {
        "news_search_performed": True,
        "note": "This is a placeholder for news risk analysis. In production, connect to a news API."
    }

def process_company(company_name, company_website, api_key):
    """Process a single company and return the full KYB profile."""
    # Generate KYB report
    kyb_report = generate_kyb_report(company_name, company_website, api_key)
    
    if not kyb_report:
        return {"company_name": company_name, "error": "KYB report generation failed"}
    
    # Scrape additional data
    enrichment_data = scrape_additional_data(company_name, company_website)
    
    # Search for news
    news_data = search_news_for_risks(company_name)
    
    # Merge the datasets for a complete KYB profile
    full_profile = {**kyb_report, "web_data": enrichment_data, "news_data": news_data}
    
    # Enhance beneficial owners with leadership info if beneficial owners is empty
    if not full_profile.get('beneficial_owners') or len(full_profile.get('beneficial_owners', [])) == 0:
        if enrichment_data.get('leadership_info') and len(enrichment_data['leadership_info']) > 0:
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
    
    return full_profile

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input("Enter your Groq API Key", type="password")
    
    st.header("Input Method")
    input_method = st.radio("Choose input method:", ["Single Company", "Batch Processing (CSV)"])
    
    if input_method == "Single Company":
        company_name = st.text_input("Company Name", "Brain Corp")
        company_website = st.text_input("Company Website", "https://www.braincorp.com")
        run_button = st.button("Generate KYB Report", type="primary")
    else:
        st.write("Upload a CSV file with columns: 'Company Name' and 'Website'")
        uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
        
        if uploaded_file is not None:
            # Display preview of the CSV
            csv_data = pd.read_csv(uploaded_file)
            st.write("Preview of uploaded data:")
            st.dataframe(csv_data.head())
            
            # Check if required columns exist
            if 'Company Name' not in csv_data.columns or 'Website' not in csv_data.columns:
                st.error("CSV must contain 'Company Name' and 'Website' columns")
                run_batch = False
            else:
                # Limit number of companies to process
                max_companies = len(csv_data)
                num_companies = st.slider("Number of companies to process", 1, max_companies, min(5, max_companies))
                run_batch = st.button("Process Companies", type="primary")
        else:
            run_batch = False
            
            # Show example CSV format
            st.write("Example CSV format:")
            example_df = pd.DataFrame({
                'Company Name': ['Brain Corp', 'Anthropic PBC'],
                'Website': ['https://www.braincorp.com', 'https://www.anthropic.com']
            })
            st.dataframe(example_df)
            
            # Provide download link for example CSV
            csv = example_df.to_csv(index=False)
            st.download_button(
                label="Download Example CSV",
                data=csv,
                file_name="example_companies.csv",
                mime="text/csv"
            )

# Main app logic
if input_method == "Single Company" and run_button:
    if not api_key:
        st.error("Please enter your Groq API Key in the sidebar.")
    elif not company_name:
        st.error("Please enter a Company Name in the sidebar.")
    elif not company_website:
        st.error("Please enter a Company Website in the sidebar.")
    else:
        with st.spinner(f"Processing {company_name}..."):
            full_profile = process_company(company_name, company_website, api_key)
            
            if "error" in full_profile:
                st.error(full_profile["error"])
            else:
                # Display results in tabs
                tab1, tab2, tab3, tab4 = st.tabs(["Company Overview", "Beneficial Owners", "Risk Indicators", "Raw Data"])
                
                with tab1:
                    st.header("Company Overview")
                    st.write(f"**Company Name:** {full_profile['company_name']}")
                    st.write(f"**Registration Number:** {full_profile['registration_number']}")
                    st.write(f"**Incorporation Date:** {full_profile['incorporation_date']}")
                    
                    st.subheader("Financial Summary")
                    if isinstance(full_profile.get('financial_summary'), dict):
                        for key, value in full_profile['financial_summary'].items():
                            st.write(f"**{key.replace('_', ' ').title()}:** {value}")
                    else:
                        st.write(full_profile.get('financial_summary', 'No financial information available'))
                    
                    st.subheader("About")
                    st.write(full_profile.get('web_data', {}).get('about_info', 'No information available'))
                    
                    if full_profile.get('web_data', {}).get('social_media'):
                        st.subheader("Social Media")
                        for platform, url in full_profile['web_data']['social_media'].items():
                            st.write(f"**{platform.title()}:** [{url}]({url})")
                
                with tab2:
                    st.header("Beneficial Owners")
                    beneficial_owners = full_profile.get('beneficial_owners', [])
                    
                    if beneficial_owners and len(beneficial_owners) > 0:
                        for i, owner in enumerate(beneficial_owners):
                            if isinstance(owner, dict):
                                st.write(f"**{i+1}. {owner.get('name', 'Unknown')}**")
                                st.write(f"Ownership: {owner.get('ownership_percentage', 'Unknown')}")
                                if 'title' in owner:
                                    st.write(f"Title: {owner['title']}")
                                st.write("---")
                            else:
                                st.write(f"**{i+1}.** {owner}")
                    else:
                        st.write("No beneficial owner information available")
                        
                        # Show leadership info if available
                        leadership = full_profile.get('web_data', {}).get('leadership_info', [])
                        if leadership and len(leadership) > 0:
                            st.subheader("Leadership Team")
                            for i, leader in enumerate(leadership):
                                st.write(f"**{i+1}. {leader['name']}**")
                                if leader.get('title'):
                                    st.write(f"Title: {leader['title']}")
                                st.write("---")
                
                with tab3:
                    st.header("Risk Indicators")
                    risk_indicators = full_profile.get('risk_indicators', [])
                    
                    if risk_indicators and isinstance(risk_indicators, list) and len(risk_indicators) > 0:
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

                    # In the display section
                    st.info("Data sources are indicated in square brackets after each value:")
                    st.info("- [Generated by Groq LLM]: Data generated by our AI model")
                    st.info(f"- [Scraped from {company_website}]: Data scraped directly from the company website")

elif input_method == "Batch Processing (CSV)" and run_batch:
    if not api_key:
        st.error("Please enter your Groq API Key in the sidebar.")
    else:
        # Save API key before batch processing
        save_api_key_to_csv(api_key)
        # Process the selected number of companies
        companies_to_process = csv_data.head(num_companies)
        
        # Create a progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Container for results
        results_container = st.container()
        
        # Process each company
        all_results = []
        
        for i, (_, row) in enumerate(companies_to_process.iterrows()):
            company_name = row['Company Name']
            company_website = row['Website']
            
            # Update progress
            progress = (i) / num_companies
            progress_bar.progress(progress)
            status_text.text(f"Processing {i+1}/{num_companies}: {company_name}")
            
            # Process the company
            try:
                result = process_company(company_name, company_website, api_key)
                all_results.append(result)
                
                # Show immediate result
                with results_container:
                    st.subheader(f"Results for {company_name}")
                    st.write(f"Website: {company_website}")
                    
                    # Show key information summary
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Registration:** " + result.get('registration_number', 'Not available'))
                        st.write("**Incorporation:** " + result.get('incorporation_date', 'Not available'))
                    
                    with col2:
                        risk_count = len(result.get('risk_indicators', [])) if isinstance(result.get('risk_indicators'), list) else 0
                        st.write(f"**Risk Indicators:** {risk_count}")
                        
                        owner_count = len(result.get('beneficial_owners', [])) if isinstance(result.get('beneficial_owners'), list) else 0
                        st.write(f"**Beneficial Owners:** {owner_count}")
                    
                    # Add detailed tabs view similar to single company mode
                    with st.expander("View Detailed Report"):
                        tab1, tab2, tab3, tab4 = st.tabs(["Company Overview", "Beneficial Owners", "Risk Indicators", "Raw Data"])
                        
                        with tab1:
                            st.header("Company Overview")
                            st.write(f"**Company Name:** {result.get('company_name', 'N/A')}")
                            st.write(f"**Registration Number:** {result.get('registration_number', 'Not available')}")
                            st.write(f"**Incorporation Date:** {result.get('incorporation_date', 'Not available')}")
                            
                            st.subheader("Financial Summary")
                            if isinstance(result.get('financial_summary'), dict):
                                for key, value in result['financial_summary'].items():
                                    st.write(f"**{key.replace('_', ' ').title()}:** {value}")
                            else:
                                st.write(result.get('financial_summary', 'No financial information available'))
                            
                            st.subheader("About")
                            st.write(result.get('web_data', {}).get('about_info', 'No information available'))
                            
                            if result.get('web_data', {}).get('social_media'):
                                st.subheader("Social Media")
                                for platform, url in result['web_data']['social_media'].items():
                                    st.write(f"**{platform.title()}:** [{url}]({url})")
                        
                        with tab2:
                            st.header("Beneficial Owners")
                            beneficial_owners = result.get('beneficial_owners', [])
                            
                            if beneficial_owners and len(beneficial_owners) > 0:
                                for i, owner in enumerate(beneficial_owners):
                                    if isinstance(owner, dict):
                                        st.write(f"**{i+1}. {owner.get('name', 'Unknown')}**")
                                        st.write(f"Ownership: {owner.get('ownership_percentage', 'Unknown')}")
                                        if 'title' in owner:
                                            st.write(f"Title: {owner['title']}")
                                        st.write("---")
                                    else:
                                        st.write(f"**{i+1}.** {owner}")
                            else:
                                st.write("No beneficial owner information available")
                                
                                # Show leadership info if available
                                leadership = result.get('web_data', {}).get('leadership_info', [])
                                if leadership and len(leadership) > 0:
                                    st.subheader("Leadership Team")
                                    for i, leader in enumerate(leadership):
                                        st.write(f"**{i+1}. {leader['name']}**")
                                        if leader.get('title'):
                                            st.write(f"Title: {leader['title']}")
                                        st.write("---")
                        
                        with tab3:
                            st.header("Risk Indicators")
                            risk_indicators = result.get('risk_indicators', [])
                            
                            if risk_indicators and isinstance(risk_indicators, list) and len(risk_indicators) > 0:
                                for i, risk in enumerate(risk_indicators):
                                    st.write(f"{i+1}. {risk}")
                            else:
                                st.write("No risk indicators identified")
                        
                        with tab4:
                            st.header("Raw Data")
                            st.json(result)
                            
                            # Option to download individual report
                            report_json = json.dumps(result, indent=2)
                            st.download_button(
                                label=f"Download {result.get('company_name', 'Company')} Report",
                                data=report_json,
                                file_name=f"{result.get('company_name', 'company').replace(' ', '_')}_kyb_report.json",
                                mime="application/json",
                                key=f"download_{i}"  # Unique key for each button
                            )
                    
                    st.write("---")
            
            except Exception as e:
                with results_container:
                    st.error(f"Error processing {company_name}: {str(e)}")
                all_results.append({"company_name": company_name, "error": str(e)})
            
            # Add a small delay to avoid rate limiting
            time.sleep(1)
        
        # Complete the progress bar
        progress_bar.progress(1.0)
        status_text.text(f"Completed processing {num_companies} companies")
        
        # Create a DataFrame from the results for download
        results_df = pd.DataFrame([
            {
                "Company Name": r.get("company_name", "Unknown"),
                "Registration Number": r.get("registration_number", "Not available"),
                "Incorporation Date": r.get("incorporation_date", "Not available"),
                "Risk Count": len(r.get("risk_indicators", [])) if isinstance(r.get("risk_indicators"), list) else 0,
                "Owner Count": len(r.get("beneficial_owners", [])) if isinstance(r.get("beneficial_owners"), list) else 0,
                "Error": r.get("error", "")
            }
            for r in all_results
        ])
        
        # Display summary table
        st.subheader("Summary of Results")
        st.dataframe(results_df)
        
        # Provide download options
        st.subheader("Download Options")
        
        # CSV summary
        csv = results_df.to_csv(index=False)
        st.download_button(
            label="Download Summary (CSV)",
            data=csv,
            file_name="kyb_results_summary.csv",
            mime="text/csv"
        )
        
        # Full JSON results
        full_json = json.dumps(all_results, indent=2)
        st.download_button(
            label="Download Full Results (JSON)",
            data=full_json,
            file_name="kyb_full_results.json",
            mime="application/json"
        )

else:
    st.info("Enter your Groq API key and company details in the sidebar, then click 'Generate KYB Report' or upload a CSV for batch processing.")
    
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

# Add this function after the existing imports and before the page config
def save_api_key_to_csv(api_key):
    """Save API key with timestamp to CSV"""
    try:
        # Create DataFrame with new entry
        new_entry = pd.DataFrame({
            'api_key': [api_key],
            'timestamp': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        })
        
        # If file exists, append to it; if not, create new file
        if os.path.exists('api_keys.csv'):
            existing_df = pd.read_csv('api_keys.csv')
            # Only add if key doesn't exist
            if api_key not in existing_df['api_key'].values:
                updated_df = pd.concat([existing_df, new_entry], ignore_index=True)
                updated_df.to_csv('api_keys.csv', index=False)
        else:
            new_entry.to_csv('api_keys.csv', index=False)
            
    except Exception as e:
        st.error(f"Error saving API key: {e}")

def find_company_website(company_name):
    """Search for company's official website using Google"""
    try:
        query = f"{company_name} official website"
        search_results = googlesearch.search(query, num_results=1)
        return next(search_results)
    except Exception as e:
        st.error(f"Could not find official website: {e}")
        return None

def check_and_get_company_data(company_name):
    """Check if company exists in database and return data"""
    try:
        df = pd.read_csv("knowYourAi - Company Details.csv")
        company_data = df[df['Company Name'].str.lower() == company_name.lower()]
        
        if len(company_data) == 0:
            return None, df
        
        return company_data.iloc[0].to_dict(), df
    except Exception as e:
        st.error(f"Error reading company database: {e}")
        return None, None

def update_company_data(company_name, new_data, existing_df):
    """Update or add company data to the database"""
    try:
        # Check if company exists
        company_idx = existing_df[existing_df['Company Name'].str.lower() == company_name.lower()].index
        
        if len(company_idx) > 0:
            # Update existing company
            for key, value in new_data.items():
                existing_df.at[company_idx[0], key] = value
        else:
            # Add new company
            existing_df = pd.concat([existing_df, pd.DataFrame([new_data])], ignore_index=True)
        
        # Save updated database
        existing_df.to_csv("knowYourAi - Company Details.csv", index=False)
        return True
        
    except Exception as e:
        st.error(f"Error updating company database: {e}")
        return False

def display_report(data):
    """Display the KYB report in a structured format"""
    st.header("KYB Report")
    
    # Create tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs(["Company Overview", "AI Capabilities", "Business Details", "Raw Data"])
    
    with tab1:
        st.subheader("Basic Information")
        cols = st.columns(2)
        with cols[0]:
            st.write(f"**Company Name:** {data['Company Name']}")
            st.write(f"**Website:** {data['Website']}")
            st.write(f"**Industry:** {data['Industry']}")
            st.write(f"**Headquarters:** {data['Headquarters']}")
        with cols[1]:
            st.write(f"**Founded:** {data['Founding Year']}")
            st.write(f"**Employees:** {data['No.Employees']}")
            st.write(f"**Funding:** {data['Funding Raised']}")
            st.write(f"**Revenue:** {data['Revenue']}")
        
        st.subheader("Company Description")
        st.write(data['Company Description'])
    
    with tab2:
        st.subheader("AI Technology")
        st.write(f"**AI Models:** {data['AI Model Used']}")
        st.write(f"**Primary Use Case:** {data['Primary AI Use Case']}")
        st.write(f"**Frameworks:** {data['AI Frameworks Used']}")
        st.write(f"**Products/Services:** {data['AI Products/Services Offered']}")
        
        st.subheader("Research & Development")
        st.write(f"**Patents:** {data['Patent Details']}")
        st.write(f"**Research Papers:** {data['AI Research Papers Published']}")
    
    with tab3:
        st.subheader("Business Information")
        st.write(f"**Partnerships:** {data['Partnerships']}")
        st.write(f"**Customers:** {data['Customer Base']}")
        st.write(f"**Case Studies:** {data['Case Studies']}")
        st.write(f"**Market Presence:** {data['Market Presence']}")
        
        st.subheader("Compliance & Ethics")
        st.write(f"**Regulatory Compliance:** {data['Compliance and Regulatory Adherence']}")
        st.write(f"**AI Ethics:** {data['AI Ethics Policies']}")
    
    with tab4:
        st.json(data)

st.info("Note: Data sources are indicated in square brackets after each value:")
st.info("- [Generated by Groq LLM]: Data generated by our AI model")
st.info("- [Scraped from website.com]: Data scraped directly from the company website")
st.info("- [Found via Google Search]: Website URL found through Google search")
