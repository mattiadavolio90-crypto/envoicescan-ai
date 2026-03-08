(function() {
    const keywords = ['deploy','share','condividi','pubblica'];
    function cleanBranding() {
        try {
            document.querySelectorAll('footer, [role="contentinfo"], [data-testid="stFooter"], [data-testid="stDecoration"], [data-testid="stToolbar"], header[data-testid="stHeader"], [class*="viewerBadge"], [data-testid="manage-app-button"], [data-testid="stStatusWidget"], [class*="stAppDeployButton"], [class*="StatusWidget"]').forEach(el => el.remove());
            document.querySelectorAll('a[href*="streamlit.io"]').forEach(el => {
                if ((el.textContent||'').match(/Made with|Streamlit/)) el.remove();
            });
            document.querySelectorAll('button, a, span').forEach(el => {
                const combined = [(el.innerText||'').toLowerCase(), (el.title||'').toLowerCase(), (el.getAttribute('aria-label')||'').toLowerCase()].join(' ');
                for (const k of keywords) { if (combined.includes(k)) { el.style.display='none'; break; } }
            });
            // Rimuovi specificamente il floating "Manage app" in basso a destra
            document.querySelectorAll('button').forEach(el => {
                if ((el.innerText||'').toLowerCase().includes('manage app')) { el.closest('div')?.remove() || el.remove(); }
            });
        } catch(e) {}
    }
    cleanBranding();
    const observer = new MutationObserver(cleanBranding);
    observer.observe(document.body, {childList:true, subtree:true});
})();
