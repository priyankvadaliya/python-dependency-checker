document.addEventListener('DOMContentLoaded', function() {
    // Tab functionality
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            // Remove active class from all tabs
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            // Add active class to clicked tab
            tab.classList.add('active');
            document.getElementById(tab.dataset.tab + 'Tab').classList.add('active');
        });
    });
    
    // Clear button
    document.getElementById('clearButton').addEventListener('click', function() {
        document.getElementById('requirementsText').value = '';
    });
    
    // Load example button
    document.getElementById('loadExampleButton').addEventListener('click', function() {
        document.getElementById('requirementsText').value = `Flask==2.2.3
Werkzeug==1.0.1  # This will conflict with Flask 2.2.3
requests==2.28.2
urllib3==2.0.3  # This will conflict with requests
pandas==1.5.3
numpy==1.20.3  # This will conflict with pandas`;
    });
    
    // Check dependencies
    document.getElementById('checkButton').addEventListener('click', function() {
        const requirementsText = document.getElementById('requirementsText').value;
        
        if (!requirementsText.trim()) {
            showNotification('Please enter package requirements', 'error');
            return;
        }
        
        // Show loading state
        document.getElementById('loading').style.display = 'flex';
        document.getElementById('result').style.display = 'none';
        
        // Send request to server
        const formData = new FormData();
        formData.append('requirements', requirementsText);
        
        fetch('/check_dependencies', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            // Hide loading state
            document.getElementById('loading').style.display = 'none';
            document.getElementById('result').style.display = 'block';
            
            // Display performance info
            if (data.execution_time) {
                document.getElementById('performanceInfo').innerHTML = `
                    <i class="fas fa-clock"></i>
                    <span>Analysis completed in ${data.execution_time}</span>
                `;
            }
            
            // Update counts
            document.getElementById('conflictsCount').textContent = data.conflicts ? data.conflicts.length : 0;
            document.getElementById('packagesCount').textContent = data.requirements ? data.requirements.length : 0;
            
            // Show the conflicts tab if conflicts exist
            if (data.conflicts && data.conflicts.length > 0) {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                document.querySelector('.tab[data-tab="conflicts"]').classList.add('active');
                document.getElementById('conflictsTab').classList.add('active');
            }
            
            // Display conflicts
            const conflictsListEl = document.getElementById('conflictsList');
            conflictsListEl.innerHTML = '';
            
            if (data.conflicts && data.conflicts.length > 0) {
                data.conflicts.forEach(conflict => {
                    const conflictEl = document.createElement('div');
                    conflictEl.className = `package ${conflict.type || 'conflict'}`;
                    
                    // Create conflict header
                    const headerEl = document.createElement('div');
                    headerEl.className = 'package-header';
                    
                    const nameEl = document.createElement('div');
                    nameEl.className = 'package-name';
                    nameEl.innerHTML = `<i class="fas fa-exclamation-circle" style="color: #f44336;"></i> ${conflict.package}`;
                    
                    const typeEl = document.createElement('div');
                    typeEl.className = 'package-type';
                    typeEl.textContent = conflict.type ? conflict.type.replace('_', ' ') : 'conflict';
                    
                    headerEl.appendChild(nameEl);
                    headerEl.appendChild(typeEl);
                    
                    // Create error message
                    const errorEl = document.createElement('div');
                    errorEl.className = 'error-message';
                    errorEl.textContent = conflict.error;
                    
                    conflictEl.appendChild(headerEl);
                    conflictEl.appendChild(errorEl);
                    
                    // Add suggestion if available
                    if (conflict.suggestion) {
                        const suggestionEl = document.createElement('div');
                        suggestionEl.className = 'suggestion';
                        
                        const suggestionHeaderEl = document.createElement('div');
                        suggestionHeaderEl.className = 'suggestion-header';
                        suggestionHeaderEl.innerHTML = '<i class="fas fa-lightbulb"></i> Suggestion';
                        
                        const suggestionTextEl = document.createElement('div');
                        suggestionTextEl.textContent = conflict.suggestion;
                        
                        suggestionEl.appendChild(suggestionHeaderEl);
                        suggestionEl.appendChild(suggestionTextEl);
                        
                        conflictEl.appendChild(suggestionEl);
                    }
                    
                    conflictsListEl.appendChild(conflictEl);
                });
            } else {
                conflictsListEl.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-check-circle" style="color: var(--success-color);"></i>
                        <h3>All Clear!</h3>
                        <p>No conflicts detected in your requirements.</p>
                    </div>
                `;
            }
            
            // Display packages
            const packagesListEl = document.getElementById('packagesList');
            packagesListEl.innerHTML = '';
            
            if (data.requirements && data.requirements.length > 0) {
                // Create a list of packages analyzed with improved styling
                packagesListEl.innerHTML = `
                    <div class="card">
                        <div class="card-body">
                            <pre>${data.requirements.join('\n')}</pre>
                        </div>
                    </div>
                `;
            } else {
                packagesListEl.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-box-open"></i>
                        <h3>No Packages</h3>
                        <p>No packages were analyzed.</p>
                    </div>
                `;
            }
            
            // Display fixed requirements if available
            if (data.fixed_requirements && data.fixed_requirements.length > 0) {
                document.getElementById('suggestedFixResult').style.display = 'block';
                const fixedRequirementsListEl = document.getElementById('fixedRequirementsList');
                fixedRequirementsListEl.textContent = data.fixed_requirements.join('\n');
                
                // Copy to clipboard button
                document.getElementById('copyFixedButton').addEventListener('click', function() {
                    navigator.clipboard.writeText(data.fixed_requirements.join('\n'))
                        .then(() => {
                            this.innerHTML = '<i class="fas fa-check btn-icon"></i> Copied!';
                            setTimeout(() => {
                                this.innerHTML = '<i class="fas fa-copy btn-icon"></i> Copy';
                            }, 2000);
                        })
                        .catch(err => showNotification('Failed to copy: ' + err, 'error'));
                });
                
                // Apply changes button
                document.getElementById('applyFixedButton').addEventListener('click', function() {
                    document.getElementById('requirementsText').value = data.fixed_requirements.join('\n');
                    showNotification('Changes applied! Click "Check Dependencies" again to verify the fix.', 'success');
                });
            } else {
                document.getElementById('suggestedFixResult').style.display = 'none';
            }
            
            // Display dependency graph
            const graphImageEl = document.getElementById('graphImage');
            graphImageEl.innerHTML = '';
            
            if (data.graph_image) {
                const img = document.createElement('img');
                img.src = 'data:image/png;base64,' + data.graph_image;
                img.alt = 'Dependency Graph';
                graphImageEl.appendChild(img);
            } else if (data.graph_error) {
                graphImageEl.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-exclamation-triangle" style="color: var(--warning-color);"></i>
                        <h3>Graph Generation Error</h3>
                        <p>${data.graph_error}</p>
                    </div>
                `;
            } else {
                graphImageEl.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-project-diagram"></i>
                        <h3>No Graph Available</h3>
                        <p>No dependency graph could be generated.</p>
                    </div>
                `;
            }
        })
        .catch(error => {
            document.getElementById('loading').style.display = 'none';
            showNotification('Error: ' + error.message, 'error');
        });
    });
    
    // Function to show notification
    function showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.style.position = 'fixed';
        notification.style.bottom = '20px';
        notification.style.right = '20px';
        notification.style.padding = '10px 20px';
        notification.style.borderRadius = '4px';
        notification.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.2)';
        notification.style.zIndex = '1000';
        
        if (type === 'error') {
            notification.style.backgroundColor = '#f44336';
            notification.style.color = 'white';
            notification.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${message}`;
        } else if (type === 'success') {
            notification.style.backgroundColor = '#4caf50';
            notification.style.color = 'white';
            notification.innerHTML = `<i class="fas fa-check-circle"></i> ${message}`;
        } else {
            notification.style.backgroundColor = '#2196f3';
            notification.style.color = 'white';
            notification.innerHTML = `<i class="fas fa-info-circle"></i> ${message}`;
        }
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }
});