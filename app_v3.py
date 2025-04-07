import os
import json
import requests
import re
from bs4 import BeautifulSoup
import streamlit as st
from groq import Groq
import pandas as pd
from datetime import datetime
import glob
from crewai import Agent, Task, Crew, Process
from transformers import pipeline
import sys
import subprocess
from langchain.tools import Tool

# File paths
CORE_DATASET_PATH = "/home/opc/myenv/YCX-KYB/knowYourAi - Company Details.csv"
USER_OUTPUT_PATH = "/home/opc/myenv/YCX-KYB/user_output.csv"
REPORTS_DIR = "/home/opc/myenv/YCX-KYB/generated_reports"

# Create reports directory if it doesn't exist
os.makedirs(REPORTS_DIR, exist_ok=True)

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

# Initialize session state
if 'admin_logged_in' not in st.session_state:
    st.session_state.admin_logged_in = False
if 'core_df' not in st.session_state:
    st.session_state.core_df = None

# Input method selection
input_choice = st.radio(
    "Choose your input method:",
    ["Enter Company Name", "Write Custom Prompt", "Admin View"]
)

# Simplified model_options with only the confirmed working models
model_options = {
    "LLaMA 3 70B": "llama3-70b-8192",
    "LLaMA 3 8B": "llama3-8b-8192",
    "LLaMA 3.3 70B Versatile": "llama-3.3-70b-versatile",
    "Mistral Saba 24B": "mistral-saba-24b"
}

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    
    selected_model = st.selectbox("Select AI Model", list(model_options.keys()))
    
    api_key = st.text_input("Enter your Groq API Key", type="password")
    st.markdown("[Generate Groq API Key](https://console.groq.com/keys)")
    
    company_name = st.text_input("Company Name (Optional)", help="Enter for single company report.")
    company_website = st.text_input("Company Website (Optional)", help="Optional for single company report.")
    custom_prompt = st.text_area("Special Instructions (Optional)", help="E.g., 'Look for companies whose name starts with M'")
    
    run_button = st.button("Generate Report", type="primary")

# Initialize the local LLM for CrewAI (Hugging Face model)
# summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

# Define Custom Tools by Subclassing BaseTool
# class ScrapeWebTool(BaseTool):
#     name: str = "Web Scraper"
#     description: str = "Scrapes additional data about a company from the web."
#
#     def _run(self, company_name: str) -> str:
#         try:
#             search_url = f"https://www.google.com/search?q={company_name}+news+site:*.org+site:*.gov+-inurl:(signup | login)"
#             headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
#             res = requests.get(search_url, headers=headers, timeout=15)
#             res.raise_for_status()
#             soup = BeautifulSoup(res.text, 'html.parser')
#             snippets = soup.find_all('div', class_='BNeawe s3v9rd AP7Wnd')  # Google search snippet class
#             text = ' '.join([snippet.get_text() for snippet in snippets[:3]])  # Take first 3 snippets
#             if not text:
#                 return "No additional data found."
#             return text
#         except Exception as e:
#             return f"Error scraping web: {str(e)}"

# class ProcessDataTool(BaseTool):
#     name: str = "Data Processor"
#     description: str = "Processes and summarizes scraped data using a local LLM."
#
#     def _run(self, text: str) -> str:
#         try:
#             summary = summarizer(text, max_length=100, min_length=30, do_sample=False)
#             return summary[0]['summary_text']
#         except Exception as e:
#             return f"Error processing data: {str(e)}"

# class SaveToCSVTool(BaseTool):
#     name: str = "CSV Writer"
#     description: str = "Saves processed data into the core dataset CSV file."
#
#     def _run(self, data: dict) -> str:
#         try:
#             company_name = data.get('company_name')
#             processed_data = data.get('processed_data')
#             if not company_name or not processed_data:
#                 return "Error: Missing company_name or processed_data"
#             new_data = pd.DataFrame({
#                 "company_name": [company_name],
#                 "additional_info": [processed_data],
#                 "timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
#             })
#             if os.path.exists(CORE_DATASET_PATH):
#                 existing_data = pd.read_csv(CORE_DATASET_PATH)
#                 updated_data = pd.concat([existing_data, new_data], ignore_index=True)
#             else:
#                 updated_data = new_data
#             updated_data.to_csv(CORE_DATASET_PATH, index=False)
#             return f"Data saved to {CORE_DATASET_PATH}"
#         except Exception as e:
#             return f"Error saving to CSV: {str(e)}"

# Instantiate the Tools
# scrape_tool = ScrapeWebTool()
# process_tool = ProcessDataTool()
# save_tool = SaveToCSVTool()

# First, define all the basic functions
def scrape_web_for_company(company_name):
    """Enhanced web scraping for company information"""
    try:
        # Search multiple sources
        sources = [
            f"https://www.google.com/search?q={company_name}+company+registration+information",
            f"https://www.google.com/search?q={company_name}+financial+results+annual+report",
            f"https://www.google.com/search?q={company_name}+executives+management+team",
            f"https://www.google.com/search?q={company_name}+news+recent+developments"
        ]
        
        all_data = []
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
        
        for search_url in sources:
            try:
        res = requests.get(search_url, headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
                snippets = soup.find_all('div', class_='BNeawe s3v9rd AP7Wnd')
                text = ' '.join([snippet.get_text() for snippet in snippets[:5]])
                if text:
                    all_data.append(text)
            except Exception as e:
                continue
        
        combined_data = ' '.join(all_data)
        return combined_data if combined_data else "No additional data found."
        
    except Exception as e:
        return f"Error scraping web: {str(e)}"

def process_data_with_llm(text, api_key, model):
    """Process the scraped data using Groq API."""
    try:
        client = Groq(api_key=api_key)
        
        system_prompt = """
        You are a data analyst processing company information. Analyze and summarize the provided text.
        Format your response as a structured JSON with these fields:
        - summary: Brief overview of key points
        - key_findings: List of important discoveries
        - risk_factors: Any potential risk indicators identified
        Ensure the response is properly formatted JSON.
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze this company information: {text}"}
        ]
        
        response = client.chat.completions.create(
            messages=messages,
            model=model,
            temperature=0.1,
            max_tokens=1024
        )
        
        output_text = response.choices[0].message.content
        return output_text
        
    except Exception as e:
        return f"Error processing data: {str(e)}"

def save_to_core_dataset(company_name, processed_data):
    """Save the processed data into the core dataset CSV."""
    try:
        new_data = pd.DataFrame({
            "company_name": [company_name],
            "additional_info": [processed_data],
            "timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        })
        if os.path.exists(CORE_DATASET_PATH):
            existing_data = pd.read_csv(CORE_DATASET_PATH)
            updated_data = pd.concat([existing_data, new_data], ignore_index=True)
        else:
            updated_data = new_data
        updated_data.to_csv(CORE_DATASET_PATH, index=False)
        return f"Data saved to {CORE_DATASET_PATH}"
    except Exception as e:
        return f"Error saving to CSV: {str(e)}"

# Then define the tools
scraping_tool = Tool(
    name="Web Scraper",
    func=scrape_web_for_company,
    description="Scrapes company information from the web"
)

processing_tool = Tool(
    name="Data Processor",
    func=lambda x: process_data_with_llm(x, api_key, model_options[selected_model]),
    description="Processes and analyzes company data"
)

saving_tool = Tool(
    name="Data Saver",
    func=save_to_core_dataset,
    description="Saves processed data to CSV"
)

# Then define the agents
scraper_agent = Agent(
    role="Web Scraper",
    goal="Find comprehensive information about the company from reliable sources.",
    backstory="""You are an expert web scraper specialized in finding accurate company 
    information from various sources. You're known for your ability to gather detailed 
    business intelligence.""",
    tools=[scraping_tool],
    verbose=True,
    allow_delegation=False
)

processor_agent = Agent(
    role="Data Analyst",
    goal="Analyze and structure company information into useful insights.",
    backstory="""You are a skilled data analyst with expertise in processing and 
    analyzing company information. You excel at identifying key business metrics 
    and risk factors.""",
    tools=[processing_tool],
    verbose=True,
    allow_delegation=False
)

writer_agent = Agent(
    role="Data Engineer",
    goal="Save and organize company information in a structured format.",
    backstory="""You are a detail-oriented data engineer who ensures all company 
    information is properly stored and organized.""",
    tools=[saving_tool],
    verbose=True,
    allow_delegation=False
)

# Then define the crew analysis function
def run_crew_analysis(company_name, api_key, model):
    """Run the CrewAI workflow for company analysis"""
    try:
        # Define tasks with more specific instructions
        scraping_task = Task(
            description=f"""Search for detailed information about {company_name}, including:
            1. Company registration details
            2. Financial information
            3. Key executives and beneficial owners
            4. Recent news and developments
            5. Any risk indicators or regulatory issues""",
            agent=scraper_agent,
            expected_output="Comprehensive company information from multiple sources",
            function=lambda: scrape_web_for_company(company_name)
        )

        processing_task = Task(
            description="""Analyze the gathered information and structure it into:
            1. Key company details
            2. Financial metrics
            3. Ownership structure
            4. Risk assessment
            Ensure all data is properly formatted and validated.""",
            agent=processor_agent,
            expected_output="Structured and analyzed company data",
            function=lambda scraped_data: process_data_with_llm(scraped_data, api_key, model)
        )

        saving_task = Task(
            description="Save the processed information in a structured format",
            agent=writer_agent,
            expected_output="Confirmation of data being saved",
            function=lambda processed_data: save_to_core_dataset(company_name, processed_data)
        )

        # Create and run the crew with sequential process
        crew = Crew(
            agents=[scraper_agent, processor_agent, writer_agent],
            tasks=[scraping_task, processing_task, saving_task],
            verbose=True,
            process=Process.sequential
        )

        result = crew.kickoff()
        return result

    except Exception as e:
        st.error(f"CrewAI workflow failed: {str(e)}")
        return None

# Function definitions (unchanged from your original code)
def generate_kyb_report(company_name, company_website, api_key, model):
    """Generate a KYB report using the selected Groq model."""
    client = Groq(api_key=api_key)
    system_prompt = (
        "You are a seasoned business analyst with expertise in KYB due diligence. "
        "When given a company name and website, gather and summarize: registration number, "
        "incorporation date, beneficial owners, key financial metrics, and public risk indicators. "
        "Output ONLY a valid JSON object with keys: company_name, registration_number, incorporation_date, "
        "beneficial_owners, financial_summary, risk_indicators. Ensure the JSON is properly formatted "
        "with correct commas and quotes. Use 'Not publicly available' for missing data."
    )
    
    user_prompt = f"Company Name: {company_name}\nWebsite: {company_website or 'N/A'}\n\n"
    user_prompt += "Please research the company and provide information in valid JSON format. Ensure all JSON syntax is correct."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        with st.spinner(f"Generating report using {model}..."):
            response = client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=0.1,
                max_tokens=1024
            )
            
        output_text = response.choices[0].message.content
        
        output_text = output_text.strip()
        if output_text.startswith("```json"):
            output_text = output_text.replace("```json", "").replace("```", "")
        
        output_text = output_text.replace("'", '"')
        output_text = re.sub(r',\s*}', '}', output_text)
        output_text = re.sub(r',\s*]', ']', output_text)
        
        try:
            kyb_report = json.loads(output_text)
        except json.JSONDecodeError as e:
            st.error(f"JSON parsing error: {str(e)}")
            st.text("Raw response:")
            st.code(output_text)
            return None
        
        kyb_report = {
            "company_name": company_name,
            "registration_number": kyb_report.get("registration_number", "Not publicly available"),
            "incorporation_date": kyb_report.get("incorporation_date", "Not publicly available"),
            "beneficial_owners": kyb_report.get("beneficial_owners", []),
            "financial_summary": kyb_report.get("financial_summary", {}),
            "risk_indicators": kyb_report.get("risk_indicators", [])
        }
        
        if not isinstance(kyb_report["beneficial_owners"], list):
            kyb_report["beneficial_owners"] = [kyb_report["beneficial_owners"]] if kyb_report["beneficial_owners"] != "Not publicly available" else []
            
        if not isinstance(kyb_report["risk_indicators"], list):
            kyb_report["risk_indicators"] = [kyb_report["risk_indicators"]] if kyb_report["risk_indicators"] != "Not publicly available" else []
            
        if not isinstance(kyb_report["financial_summary"], dict):
            kyb_report["financial_summary"] = {"details": str(kyb_report["financial_summary"])}
            
        return kyb_report
        
    except Exception as e:
        st.error(f"Failed to generate report: {str(e)}")
        return None

def scrape_additional_data(company_website):
    """Scrape additional data from the company website."""
    if not company_website:
        return {"about_info": "N/A"}
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
        res = requests.get(company_website, headers=headers, timeout=15)
        res.raise_for_status()
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
        return {"about_info": about_text[:500]}
    except Exception as e:
        st.error(f"Scraping failed: {str(e)}")
        return {"about_info": "Failed to retrieve data"}

def save_report(company_name, report_data):
    """Save report to JSON file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{company_name.replace(' ', '_')}_{timestamp}.json"
    filepath = os.path.join(REPORTS_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(report_data, f, indent=2)

def update_user_output(api_key, input_type, input_text, timestamp):
    """Update user_output.csv with usage data"""
    data = {
        'api_key': [api_key],
        'input_type': [input_type],
        'input_text': [input_text],
        'timestamp': [timestamp]
    }
    new_entry = pd.DataFrame(data)
    
    try:
        if os.path.exists(USER_OUTPUT_PATH):
            df = pd.read_csv(USER_OUTPUT_PATH)
            df = pd.concat([df, new_entry], ignore_index=True)
        else:
            df = new_entry
        df.to_csv(USER_OUTPUT_PATH, index=False)
    except Exception as e:
        st.error(f"Failed to update user_output.csv: {e}")

def load_core_dataset():
    """Load core dataset if it exists."""
    try:
        if os.path.exists(CORE_DATASET_PATH):
            st.session_state.core_df = pd.read_csv(CORE_DATASET_PATH)
            return st.session_state.core_df
        return None
    except Exception as e:
        st.error(f"Failed to load core dataset: {str(e)}")
        return None

# Main logic section
if input_choice == "Admin View":
    with st.form("admin_login"):
        st.subheader("Admin Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            if username == "ycxadmin" and password == "ycxadmin":
                st.session_state.admin_logged_in = True
                st.success("Logged in as admin!")
            else:
                st.error("Invalid credentials.")

elif input_choice == "Enter Company Name" and run_button:
    try:
        if not api_key:
            st.error("Please enter your Groq API Key.")
        elif not company_name:
            st.error("Please enter a Company Name.")
        else:
            # Load core dataset
            df = load_core_dataset()
            
            # Run CrewAI analysis with API key and model
            with st.spinner("Running CrewAI analysis..."):
                crew_result = run_crew_analysis(
                    company_name, 
                    api_key, 
                    model_options[selected_model]
                )
                if crew_result:
                    st.success("CrewAI analysis completed!")
                    st.write("Additional data gathered:", crew_result)
            
            # Generate KYB report
            with st.spinner(f"Processing {company_name}..."):
                kyb_report = generate_kyb_report(
                    company_name=company_name,
                    company_website=company_website,
                    api_key=api_key,
                    model=model_options[selected_model]
                )
                if kyb_report:
                    save_report(company_name, kyb_report)
                    update_user_output(
                        api_key=api_key,
                        input_type="company_name",
                        input_text=company_name,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    display_report(kyb_report)
    except Exception as e:
        st.error(f"Error: {e}")

elif input_choice == "Write Custom Prompt" and run_button:
    try:
        if not api_key:
            st.error("Please enter your Groq API Key.")
        elif not custom_prompt:
            st.error("Please enter your prompt.")
        else:
            result_df = process_prompt(custom_prompt, None, api_key, model_options[selected_model])
            if result_df is not None and not result_df.empty:
                st.success("Results found!")
                st.dataframe(result_df, use_container_width=True)
            else:
                st.warning("No results from prompt.")
    except Exception as e:
        st.error(f"Error processing prompt: {e}")

else:
    if not st.session_state.admin_logged_in:
        st.info("Select an input method and click 'Generate Report' to proceed.")

def display_report(report_data):
    """Display the KYB report in a structured format"""
    st.header("KYB Report")
    
    # Basic Information
    st.subheader("Basic Information")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Company Name:** {report_data.get('company_name', 'N/A')}")
        st.write(f"**Registration Number:** {report_data.get('registration_number', 'N/A')}")
    with col2:
        st.write(f"**Incorporation Date:** {report_data.get('incorporation_date', 'N/A')}")
    
    # Financial Summary
    st.subheader("Financial Summary")
    financial_summary = report_data.get('financial_summary', {})
    if isinstance(financial_summary, dict):
        for key, value in financial_summary.items():
            st.write(f"**{key.replace('_', ' ').title()}:** {value}")
    else:
        st.write(financial_summary)
    
    # Beneficial Owners
    st.subheader("Beneficial Owners")
    beneficial_owners = report_data.get('beneficial_owners', [])
    if beneficial_owners:
        for owner in beneficial_owners:
            if isinstance(owner, dict):
                st.write(f"- **{owner.get('name', 'Unknown')}** ({owner.get('ownership_percentage', 'Unknown')})")
            else:
                st.write(f"- {owner}")
    else:
        st.write("No beneficial owners information available")
    
    # Risk Indicators
    st.subheader("Risk Indicators")
    risk_indicators = report_data.get('risk_indicators', [])
    if risk_indicators:
        for risk in risk_indicators:
            st.write(f"- {risk}")
    else:
        st.write("No risk indicators identified")
    
    # Raw JSON
    with st.expander("View Raw JSON"):
        st.json(report_data)