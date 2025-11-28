// --- Help Tab Functions ---

document.getElementById('help-tab').addEventListener('click', async () => {
    const helpContentDiv = document.getElementById('help');
    
    // Check if content is already loaded
    if (helpContentDiv.querySelector('.prose')) {
        return;
    }

    try {
        const response = await fetch('/static/help.html');
        if (!response.ok) {
            throw new Error('Failed to load help content.');
        }
        const htmlContent = await response.text();
        helpContentDiv.innerHTML = DOMPurify.sanitize(htmlContent);
    } catch (error) {
        helpContentDiv.innerHTML = '<p class="text-red-500">Error loading help content.</p>';
        console.error('Error fetching help content:', error);
    }
});
