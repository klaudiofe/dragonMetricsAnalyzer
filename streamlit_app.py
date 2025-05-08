# Dragon Metrics Traffic Analyzer - Streamlit App (v1.1)
import streamlit as st
import pandas as pd
from urllib.parse import urlparse
import io
import base64
import re
import advertools as adv

# Set page title and configuration
st.set_page_config(page_title="Dragon Metrics Traffic Analyzer", layout="centered")

# Sidebar - Instructions and Configuration
with st.sidebar:
    st.header("Instructions")
    st.markdown("""
    1. Go to Dragon Metrics > Organic Rankings: [Organic Keywords](https://app.dragonmetrics.com/competitor-research/ranking/organic/keywords?url=www.google.com.cn&country=cn&context=SubDomain)
    2. Click "Export to Excel" and download the file
    3. Upload your downloaded file below
    4. Configure parameters if needed
    5. Click "Analyze Traffic Data" to see results
    """)

# File upload section
st.header("Upload Data")
uploaded_file = st.file_uploader("Upload Dragon Metrics Excel file", type=["xlsx", "xls"])

# Helper function to extract subfolders
def extract_subfolders(url):
    path = urlparse(url).path.strip('/')
    return path.split('/')

# Refactored processing function
#def process_traffic_data(df, url_column, traffic_column, keyword_column, url_match, search_keywords, min_traffic):
def process_traffic_data(df, url_column, traffic_column, keyword_column, url_match, search_keywords):
    search_keywords_list = [kw.strip() for kw in search_keywords.split(',') if kw.strip()]

    required_columns = [url_column, traffic_column, keyword_column]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        st.error(f"Error: The following columns are missing: {', '.join(missing_columns)}")
        return None

    if url_match.strip():
        df["URL Match"] = df[url_column].str.contains(re.escape(url_match.strip()), case=False, na=False)
    else:
        df["URL Match"] = False

    if search_keywords_list:
        keyword_pattern = '|'.join(map(re.escape, search_keywords_list))
        df["Translation Match"] = df[keyword_column].str.contains(keyword_pattern, case=False, na=False)
    else:
        df["Translation Match"] = False

    if not url_match.strip() and not search_keywords_list:
        st.warning("Both URL path and keywords are empty. Please provide at least one.")
        return None

    df["Category"] = "No Match"
    df.loc[df["URL Match"] & ~df["Translation Match"], "Category"] = "URL matches only"
    df.loc[~df["URL Match"] & df["Translation Match"], "Category"] = "Translation matches only"
    df.loc[df["URL Match"] & df["Translation Match"], "Category"] = "Both matches"

    filtered_df = df[df["Category"] != "No Match"].copy()
    #filtered_df = filtered_df[filtered_df[traffic_column] >= min_traffic]

    # Reorder columns: move match flags and category just before keyword column
    cols = filtered_df.columns.tolist()
    if keyword_column in cols:
        idx = cols.index(keyword_column)
        for col in ["URL Match", "Translation Match", "Category"]:
            if col in cols:
                cols.remove(col)
        new_order = cols[:idx] + ["URL Match", "Translation Match", "Category"] + cols[idx:]
        filtered_df = filtered_df[new_order]

    return filtered_df

# Create a download link for the results
def get_table_download_link(df, filename="results.xlsx"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    processed_data = output.getvalue()
    b64 = base64.b64encode(processed_data).decode()
    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}">Download Results Excel File</a>'
    return href

# Add new function for subfolder analysis
def analyze_subfolders(df, url_column, traffic_column):
    # Create a copy of the dataframe to avoid modifying the original
    analysis_df = df.copy()
    
    # Clean URL column - replace NaN with empty string
    analysis_df[url_column] = analysis_df[url_column].fillna('')
    
    # Use advertools to parse URLs
    url_df = adv.url_to_df(analysis_df[url_column])
    
    # Merge the parsed URL data with the original dataframe
    analysis_df = pd.concat([analysis_df, url_df], axis=1)
    
    # Group by path and calculate traffic metrics
    subfolder_analysis = analysis_df.groupby('path').agg({
        traffic_column: ['sum', 'count']
    }).reset_index()
    
    # Flatten the multi-level columns
    subfolder_analysis.columns = ['Subfolder', 'Total Traffic', 'Number of URLs']
    
    # Sort by total traffic
    subfolder_analysis = subfolder_analysis.sort_values('Total Traffic', ascending=False)
    
    # Create progressive path analysis
    progressive_paths = []
    
    # Get all unique paths and filter out empty paths
    all_paths = [path for path in analysis_df['path'].unique() if path and not pd.isna(path)]
    
    for path in all_paths:
        # Split the path into components
        components = path.strip('/').split('/')
        
        # Create progressive paths
        for i in range(1, len(components) + 1):
            progressive_path = '/' + '/'.join(components[:i]) + '/'
            progressive_paths.append(progressive_path)
    
    # Create a new dataframe with progressive paths
    progressive_df = pd.DataFrame({'progressive_path': progressive_paths})
    
    # Function to create progressive paths for a single URL
    def create_progressive_paths(path):
        if pd.isna(path) or not path:
            return []
        components = path.strip('/').split('/')
        return ['/' + '/'.join(components[:i]) + '/' for i in range(1, len(components) + 1)]
    
    # Create progressive paths for each URL
    analysis_df['progressive_paths'] = analysis_df['path'].apply(create_progressive_paths)
    
    # Explode the progressive paths into separate rows
    exploded_df = analysis_df.explode('progressive_paths')
    
    # Group by progressive path and calculate metrics
    progressive_analysis = exploded_df.groupby('progressive_paths').agg({
        traffic_column: ['sum', 'count']
    }).reset_index()
    
    # Flatten the multi-level columns
    progressive_analysis.columns = ['Subfolder', 'Total Traffic', 'Number of URLs']
    
    # Calculate total traffic and URLs for percentage calculations
    total_traffic = progressive_analysis['Total Traffic'].sum()
    total_urls = progressive_analysis['Number of URLs'].sum()
    
    # Calculate percentages
    progressive_analysis['Traffic Split'] = (progressive_analysis['Total Traffic'] / total_traffic * 100).round(2)
    progressive_analysis['URL Split'] = (progressive_analysis['Number of URLs'] / total_urls * 100).round(2)
    
    # Format the percentage columns
    progressive_analysis['Traffic Split'] = progressive_analysis['Traffic Split'].apply(lambda x: f"{x}%")
    progressive_analysis['URL Split'] = progressive_analysis['URL Split'].apply(lambda x: f"{x}%")
    
    # Sort by total traffic
    progressive_analysis = progressive_analysis.sort_values('Total Traffic', ascending=False)
    
    return subfolder_analysis, progressive_analysis

# Main analysis section
if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file)
        column_names = df.columns.tolist()

        # Data preview
        st.subheader("Preview of Uploaded Data")
        st.dataframe(df.head(10))

        # Sidebar form for parameters
        with st.sidebar.form("parameter_form"):
            st.header("Configure Parameters")
            url_column = st.selectbox("Select URL Column", options=column_names, index=column_names.index("Ranking URL") if "Ranking URL" in column_names else 0)
            traffic_column = st.selectbox("Select Traffic Column", options=column_names, index=column_names.index("Traffic Index") if "Traffic Index" in column_names else 0)
            keyword_column = st.selectbox("Select Keyword Column", options=column_names, index=column_names.index("Translation") if "Translation" in column_names else 0)
            url_match = st.text_input("URL Path to Match", value="/compressors")
            search_keywords = st.text_input("Keywords to Match (comma separated)", value="compressor")
            #min_traffic = st.slider("Minimum Traffic Threshold", 0, int(df[traffic_column].max()), 0)
            submitted = st.form_submit_button("Analyze Traffic Data")

        if submitted:
            with st.spinner("Analyzing data..."):
                st.success(f"Successfully loaded file with {len(df)} rows")

                filtered_df = process_traffic_data(df, url_column, traffic_column, keyword_column, url_match, search_keywords)
                #filtered_df = process_traffic_data(df, url_column, traffic_column, keyword_column, url_match, search_keywords, min_traffic)

                if filtered_df is not None and not filtered_df.empty:
                    st.header("Analysis Results")

                    url_only = filtered_df[filtered_df["Category"] == "URL matches only"][traffic_column].sum()
                    keyword_only = filtered_df[filtered_df["Category"] == "Translation matches only"][traffic_column].sum()
                    both_matches = filtered_df[filtered_df["Category"] == "Both matches"][traffic_column].sum()
                    total_relevant_traffic = url_only + keyword_only + both_matches

                    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
                    metric_col1.metric("URL Matches Only", f"{int(url_only)}")
                    metric_col2.metric("Translation Matches Only", f"{int(keyword_only)}")
                    metric_col3.metric("Both Matches", f"{int(both_matches)}")
                    metric_col4.metric("TOTAL Relevant Traffic", f"{int(total_relevant_traffic)}")

                    # Add Subfolder Analysis Section
                    st.subheader("Subfolder Traffic Analysis")
                    subfolder_analysis, progressive_analysis = analyze_subfolders(filtered_df, url_column, traffic_column)
                    
                    # Display path analysis
                    st.subheader("Full Path Analysis")
                    st.dataframe(subfolder_analysis)
                    
                    # Display progressive subfolder analysis
                    st.subheader("Progressive Subfolder Analysis")
                    st.dataframe(progressive_analysis)
                    
                    # Create a bar chart for top subfolders by traffic
                    top_subfolders = progressive_analysis.head(10)  # Show top 10 subfolders
                    st.subheader("Top 10 Subfolders by Traffic")
                    st.bar_chart(top_subfolders.set_index('Subfolder')['Total Traffic'])

                    summary_df = pd.DataFrame({
                        "Dimension": ["URL matches only", "Translation matches only", "URL AND Translation matches", "TOTAL relevant traffic (URL OR Translation)"],
                        "Traffic": [url_only, keyword_only, both_matches, total_relevant_traffic],
                        "Meaning": ["Traffic where only the URL matched", 
                                   "Traffic where only the Keyword matched", 
                                   "Traffic where both conditions were met", 
                                   "Sum of all traffic matching either condition"]
                    })

                    st.subheader("Summary Table")
                    st.dataframe(summary_df)

                    st.subheader("Filtered Results")
                    st.dataframe(filtered_df)

                    st.markdown(get_table_download_link(filtered_df, "dragon_metrics_results.xlsx"), unsafe_allow_html=True)

                    st.subheader("Traffic Distribution")
                    chart_data = pd.DataFrame({
                        "Category": ["URL matches only", "Translation matches only", "Both matches"],
                        "Traffic": [url_only, keyword_only, both_matches]
                    })
                    st.bar_chart(chart_data.set_index("Category"))
                else:
                    st.warning("No matching data found. Try adjusting your parameters.")
    except Exception as e:
        st.error(f"Error processing file: {e}")
else:
    st.info("Please upload an Excel file to continue")
