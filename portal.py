"""Onboarding portal: a thin UI over the pipeline API."""
import pandas as pd
import requests
import streamlit as st

import os
API = os.environ.get("API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Sentinel Onboarding Portal", layout="wide")
st.title("Customer Data Onboarding")

tab_onboard, tab_exceptions, tab_history = st.tabs(
    ["1. Onboard a file", "2. Exception queue", "3. Mapping history"]
)

with tab_onboard:
    col1, col2 = st.columns(2)
    customer = col1.text_input("Customer", "acme")
    source_system = col2.text_input("Source system", "crm")
    uploaded = st.file_uploader("Upload a sample CSV", type="csv")

    if uploaded:
        st.dataframe(pd.read_csv(uploaded, dtype=str).head(), use_container_width=True)
        uploaded.seek(0)

        if st.button("Profile and propose mapping", type="primary"):
            with st.spinner("Profiling data and proposing a mapping..."):
                response = requests.post(
                    f"{API}/mappings/propose",
                    files={"file": (uploaded.name, uploaded.getvalue(), "text/csv")},
                    data={"customer": customer, "source_system": source_system},
                )
            if response.ok:
                st.session_state.proposal = response.json()
            else:
                st.error(response.text)

    proposal = st.session_state.get("proposal")
    if proposal:
        st.subheader(f"Proposed mapping — spec {proposal['spec_id']}, version {proposal['version']}")
        st.caption("Nothing is transformed until you approve. Review each field below.")

        for field in proposal["fields"]:
            icon = {"confident": "🟢", "uncertain": "🟡", "unmapped": "🔴"}[field["status"]]
            label = f"{icon} **{field['canonical_field']}** ← `{field['source_column']}` "
            label += f"({field['confidence']:.0%}, {field.get('agreement', 'n/a')})"
            with st.expander(label, expanded=field["status"] != "confident"):
                st.write(field["reason"])
                st.code(" → ".join(field["suggested_transforms"]) or "no transforms")
                for note in field["notes"]:
                    st.warning(note)

        if proposal["unmapped_source_columns"]:
            st.info(f"Unused source columns: {', '.join(proposal['unmapped_source_columns'])}")

        approver = st.text_input("Approve as", "saad@sentinel.io")
        if st.button("Approve this mapping", type="primary"):
            response = requests.post(
                f"{API}/mappings/{proposal['spec_id']}/approve",
                json={"approved_by": approver, "overrides": []},
            )
            if response.ok:
                st.success(f"Approved as version {response.json()['version']}")
                st.session_state.approved_spec = proposal["spec_id"]
            else:
                st.error(response.json()["detail"])

    spec_id = st.session_state.get("approved_spec")
    if spec_id:
        st.divider()
        st.subheader("Run the pipeline")
        run_file = st.file_uploader("Upload the full data file", type="csv", key="runfile")
        if run_file and st.button("Run pipeline", type="primary"):
            response = requests.post(
                f"{API}/pipeline/{spec_id}/run",
                files={"file": (run_file.name, run_file.getvalue(), "text/csv")},
            )
            if response.status_code == 409:
                drift = response.json()["detail"]
                st.error("Schema drift detected — the pipeline refused to run.")
                for broken in drift["broken_fields"]:
                    st.warning(
                        f"**{broken['canonical_field']}** broke: {broken['problem']}. "
                        f"{broken['suggestion']}"
                    )
                st.caption(f"New columns seen: {', '.join(drift['new_columns']) or 'none'}")
            elif response.ok:
                result = response.json()
                c1, c2, c3 = st.columns(3)
                c1.metric("Rows", result["total_rows"])
                c2.metric("Loaded", result["valid_count"])
                c3.metric("Exceptions", result["exception_count"])
                load = result["load"]
                if load["is_replay"]:
                    st.info(
                        f"Replay detected. Inserted {load['records_inserted']}, "
                        f"unchanged {load['records_unchanged']} — no duplicates created."
                    )
            else:
                st.error(response.text)

with tab_exceptions:
    status_filter = st.selectbox("Status", ["open", "fixed", "waived", "all"])
    params = {} if status_filter == "all" else {"status": status_filter}
    try:
        response = requests.get(f"{API}/exceptions", params=params, timeout=5)
        response.raise_for_status()
        exceptions = response.json()
    except requests.RequestException:
        st.error(f"Cannot reach the API at {API}. Is it running?")
        exceptions = []

    if not exceptions:
        st.success("No exceptions with this status.")
    for exception in exceptions:
        with st.expander(f"Row {exception['row']} — {exception['rule_id']} on `{exception['field']}`"):
            st.error(exception["reason"])
            st.info(f"Suggested fix: {exception['suggested_fix']}")
            st.json(exception["record"], expanded=False)

            if exception["status"] == "open":
                col1, col2 = st.columns(2)
                value = col1.text_input("Corrected value", key=f"v{exception['id']}")
                note = col2.text_input("Note", key=f"n{exception['id']}")
                b1, b2 = st.columns(2)
                if b1.button("Fix and load", key=f"f{exception['id']}"):
                    response = requests.post(
                        f"{API}/exceptions/{exception['id']}/resolve",
                        json={"action": "fix", "resolved_by": "saad@sentinel.io",
                              "note": note, "corrected_value": value},
                    )
                    st.success("Fixed and loaded") if response.ok else st.error(response.json()["detail"])
                    st.rerun()
                if b2.button("Waive", key=f"w{exception['id']}"):
                    response = requests.post(
                        f"{API}/exceptions/{exception['id']}/resolve",
                        json={"action": "waive", "resolved_by": "saad@sentinel.io", "note": note},
                    )
                    st.success("Waived") if response.ok else st.error(response.json()["detail"])
                    st.rerun()
            else:
                st.caption(
                    f"{exception['status']} by {exception['resolved_by']} — {exception['resolution_note']}"
                )

with tab_history:
    spec = st.number_input("Spec ID", min_value=1, value=1, step=1)
    if st.button("Load version history"):
        versions = requests.get(f"{API}/mappings/{spec}/versions").json()
        for version in versions:
            badge = {"approved": "✅", "superseded": "📦", "proposed": "📝"}.get(version["status"], "")
            st.write(f"{badge} **v{version['version']}** — {version['status']} — "
                     f"fingerprint `{version['source_fingerprint']}`")
            if version["approved_by"]:
                st.caption(f"Approved by {version['approved_by']}")
            if version["diff"]:
                st.json(version["diff"], expanded=False)
            st.divider()