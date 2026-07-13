import streamlit as st
from main import analyze_document,extract_text_from_pdf,clean_text, check_default_bail

st.title("Know Your Rights")
st.caption("Indian Legal Notice & Procedural Compliance Analyzer")
st.write("test")
st.write("Upload a legal notice PDF for analysis (currently supports Banking & Cheque Bounce notices, Police&Criminal Processes, and Procedures under 106/107 BNSS)")

uploaded_file= st.file_uploader("Choose a PDF", type="pdf")

if uploaded_file is not None :
    with open("temp_uploaded.pdf","wb") as f:
        f.write(uploaded_file.getbuffer())
    
    if st.button("Analyze"):
        with st.spinner("Analyzing..."):
            document_text= clean_text(extract_text_from_pdf("temp_uploaded.pdf"))
            st.session_state["result"] = analyze_document(document_text)
            
            
    if "result" in st.session_state:
        result = st.session_state["result"]
        
        
        st.subheader("Classification")
        st.json(result["classification"])
        
        st.subheader("Missing Information")
        st.json(result["missing_info"])
        
        st.subheader("Document Checklist")
        st.json(result["checklist"])
        
        st.subheader("Compliance Check")
        st.json(result["compliance"])
        
        st.subheader("Urgency & Action Plan")
        st.json(result["urgency"])
        
        default_bail_check = next(
        (c for c in result ["compliance"].get("compliance_checks",[] )if "Default bail" in c["requirement"]),
         None
         
        )
        if default_bail_check and default_bail_check["status"] in ("Cannot Determine", "May be Non-Compliant"):
            st.subheader("One More Question")
            st.write("This document alone could't fully resolve the default-bail deadline.")
            chargesheet_answer = st.radio("Has a chargesheet been filed in this case?", ["Not yet/ Dont know", "Yes"])
            if chargesheet_answer== "Yes":
                user_cs_date= st.date_input("Chargesheet filing date")
                updated_check= check_default_bail(
                    result["extracted_fields"],
                    user_chargesheet_date= user_cs_date.strftime("%d-%m-%Y")
                    
                )
                st.write("Updated result:")
                st.json(updated_check)
                
                
                                           
            
        
        
        
        
        
        
        
        
        
    
