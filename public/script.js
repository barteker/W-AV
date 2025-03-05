const statusEl = document.getElementById('status');
const params = new URLSearchParams(window.location.search);
const token = params.get('token');

if (!token) {
    statusEl.textContent = 'No token found, redirecting...';
    window.location.href = '/auto-login';
} else {
    statusEl.textContent = 'Token found, initializing player...';
}

// Move socket initialization outside of onSpotifyWebPlaybackSDKReady
const socket = io();

window.onSpotifyWebPlaybackSDKReady = () => {
    statusEl.textContent = 'SDK Ready, creating player...';

    const player = new Spotify.Player({
        name: 'W/AV Device',
        getOAuthToken: cb => { cb(token); },
        volume: 0.5
    });

    // Add not ready listener
    player.addListener('not_ready', ({ device_id }) => {
        console.log('Device ID has gone offline', device_id);
        statusEl.textContent = 'Device went offline, trying to reconnect...';
    });

    // Update ready listener
    player.addListener('ready', ({ device_id }) => {
        statusEl.textContent = 'Player ready, checking premium status...';

        // Check premium status first
        fetch('/check-premium', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        })
            .then(response => response.json())
            .then(data => {
                if (data.isPremium) {
                    return fetch('/register-device', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ device_id })
                    });
                } else {
                    throw new Error('Premium account required');
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    statusEl.textContent = 'Device registered successfully';
                    document.getElementById('prevBtn').disabled = false;
                    document.getElementById('playPauseBtn').disabled = false;
                    document.getElementById('nextBtn').disabled = false;
                }
            })
            .catch(error => {
                statusEl.textContent = 'Error: ' + error.message;
                statusEl.classList.add('error');
            });

        loadLibraryContent('playlists');
    });

    player.addListener('initialization_error', ({ message }) => {
        statusEl.textContent = 'Initialization Error: ' + message;
        statusEl.classList.add('error');
    });

    player.addListener('authentication_error', ({ message }) => {
        statusEl.textContent = 'Authentication Error: ' + message;
        statusEl.classList.add('error');
        setTimeout(() => window.location.href = '/login', 2000);
    });

    player.addListener('account_error', ({ message }) => {
        statusEl.textContent = 'Account Error: ' + message;
        statusEl.classList.add('error');
    });

    // Connect to the player
    statusEl.textContent = 'Connecting to Spotify...';
    player.connect().then(success => {
        if (success) {
            statusEl.textContent = 'Connected to Spotify';
        } else {
            statusEl.textContent = 'Failed to connect to Spotify';
            statusEl.classList.add('error');
        }
    }).catch(error => {
        statusEl.textContent = 'Connection Error: ' + error.message;
        statusEl.classList.add('error');
    });

    player.addListener('player_state_changed', state => {
        if (state) {
            document.getElementById('nowPlaying').textContent =
                `Now Playing: ${state.track_window.current_track.name}`;
            document.getElementById('playPauseBtn').textContent =
                state.paused ? 'Play' : 'Pause';
        }
    });

    // Control buttons
    document.getElementById('playPauseBtn').onclick = () => {
        player.togglePlay();
    };

    document.getElementById('prevBtn').onclick = () => {
        player.previousTrack();
    };

    document.getElementById('nextBtn').onclick = () => {
        player.nextTrack();
    };

    setInterval(() => {
        fetch('/refresh-token')
            .then(response => response.json())
            .then(data => {
                if (data.token) {
                    window.location.reload();
                }
            })
            .catch(error => {
                statusEl.textContent = 'Token refresh failed';
            });
    }, 30 * 60 * 1000);





    // Update audio processing when playback state changes
    player.addListener('player_state_changed', state => {
        if (state && state.track_window.current_track) {
            // Get the audio element (this requires some browser-specific handling)
            const audioElement = document.querySelector('audio');
            if (audioElement) {
                const source = audioContext.createMediaElementSource(audioElement);
                source.connect(sourceNode);
            }
        }
    });

    // Add this to your JavaScript
    document.getElementById('reset-eq').onclick = () => {
        equalizer.forEach((filter, index) => {
            filter.gain.value = 0;
            document.getElementById(`eq-${frequencies[index]}`).value = 0;
        });
    };

    // Add pagination handlers
    let currentPage = 0;
    const itemsPerPage = 20;

    document.getElementById('nextPage').onclick = () => {
        currentPage++;
        loadLibraryContent(currentTab, currentPage * itemsPerPage);
    };

    document.getElementById('prevPage').onclick = () => {
        if (currentPage > 0) {
            currentPage--;
            loadLibraryContent(currentTab, currentPage * itemsPerPage);
        }
    };

    // Update loadLibraryContent function to handle pagination
    function loadLibraryContent(tab, offset = 0) {
        const contentDiv = document.getElementById('library-content');
        contentDiv.innerHTML = 'Loading...';
        
        // Clear any existing library items first
        document.querySelectorAll('.library-item').forEach(item => {
            item.remove();
        });

        fetch(`/${tab}?offset=${offset}&limit=${itemsPerPage}`)
            .then(response => response.json())
            .then(items => {
                renderLibraryItems(items, tab);

                // Show/hide pagination buttons
                document.getElementById('prevPage').style.display =
                    offset > 0 ? 'inline-block' : 'none';
                
                // Dispatch an event to signal that content is loaded
                document.dispatchEvent(new CustomEvent('library-content-loaded'));
                console.log('Library content loaded for tab:', tab);
            })
            .catch(error => {
                contentDiv.innerHTML = `Error loading ${tab}: ${error.message}`;
                console.error('Failed to load library content:', error);
            });
    }

    // Handle WebSocket updates
    socket.on('display-update', (data) => {
        updateLibraryDisplay(data.items);
        // Highlight selected item
        document.querySelectorAll('.library-item').forEach((item, index) => {
            item.classList.toggle('selected', index === data.current_item);
        });
    });

    // Update the socket.io handler in your JavaScript
    socket.on('interface-update', (data) => {
        if (data.select_tab) {
            // Actually switch tabs and load content
            const tabButtons = document.querySelectorAll('.tab-btn');
            tabButtons[data.tab].click();
        } else {
            // Just highlight the selection
            if (data.item <= 2) {
                // Highlight tab
                document.querySelectorAll('.tab-btn').forEach((btn, index) => {
                    btn.classList.toggle('highlighted', index === data.tab);
                });
            } else {
                // Highlight library item
                const items = document.querySelectorAll('.library-item');
                items.forEach((item, index) => {
                    item.classList.toggle('selected', index === (data.item - 3));
                });

                // Scroll into view if needed
                const selectedItem = items[data.item - 3];
                if (selectedItem) {
                    selectedItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            }
        }
    });
};

// Add logout button handler
document.getElementById('logoutBtn').onclick = () => {
    fetch('/logout', {
        method: 'POST',
        credentials: 'same-origin'
    })
        .then(() => {
            // Clear any client-side data
            localStorage.clear();
            sessionStorage.clear();
            // Force reload from server
            window.location.href = '/login';
        })
        .catch(error => {
            console.error('Logout failed:', error);
            // Fallback to direct login redirect
            window.location.href = '/login';
        });
};

// Make sure these are at the global level for access by all functions
let currentTab = 'playlists';
let currentPage = 0;
const itemsPerPage = 20;

// Add tab switching logic
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.onclick = () => {
        // Update tab state
        document.querySelectorAll('.tab-btn').forEach(b => {
            b.classList.remove('active');
            b.classList.remove('highlighted');
        });
        btn.classList.add('active');
        currentTab = btn.dataset.tab;
        currentPage = 0; // Reset page when changing tabs
        
        // Load the content
        const tabContentType = currentTab === 'songs' ? 'liked-songs' : currentTab;
        loadLibraryContent(tabContentType);
        
        // Log the action for debugging
        console.log('Tab clicked:', currentTab);
        
        // This is important - dispatch a custom event that our ui-update handler can detect
        document.dispatchEvent(new CustomEvent('tab-content-loading'));
    };
});

// Update loadLibraryContent function to handle pagination
function loadLibraryContent(tab, offset = 0) {
    const contentDiv = document.getElementById('library-content');
    contentDiv.innerHTML = 'Loading...';

    fetch(`/${tab}?offset=${offset}&limit=${itemsPerPage}`)
        .then(response => response.json())
        .then(items => {
            renderLibraryItems(items, tab);

            // Show/hide pagination buttons
            document.getElementById('prevPage').style.display =
                offset > 0 ? 'inline-block' : 'none';
        })
        .catch(error => {
            contentDiv.innerHTML = `Error loading ${tab}: ${error.message}`;
        });
}

function renderLibraryItems(items, tab) {
    const contentDiv = document.getElementById('library-content');

    // Add back button at the top
    let html = `
                <div class="back-button library-item" data-action="back">
                    <div>↑ Back to Tabs</div>
                </div>
            `;

    // Add library items
    html += items.map((item, index) => {
        if (tab === 'albums') {
            const album = item.album;
            return `
                        <div class="library-item" data-uri="${album.uri}" data-index="${index}">
                            <img src="${album.images[0]?.url || 'default-cover.png'}" alt="Cover">
                            <div>
                                <div>${album.name}</div>
                                <div class="artist">${album.artists[0]?.name || 'Unknown Artist'}</div>
                            </div>
                        </div>
                    `;
        } else {
            return `
                        <div class="library-item" data-uri="${item.uri || item.track?.uri}" data-index="${index}">
                            <img src="${item.images?.[0]?.url || item.track?.album?.images?.[0]?.url || 'default-cover.png'}" 
                                 alt="Cover">
                            <div>
                                <div>${item.name || item.track?.name}</div>
                                <div class="artist">
                                    ${item.owner?.display_name || item.artists?.[0]?.name ||
                item.track?.artists?.[0]?.name || 'Unknown'}
                                </div>
                            </div>
                        </div>
                    `;
        }
    }).join('');

    contentDiv.innerHTML = html;

    // Add click handler for back button
    const backButton = document.querySelector('.back-button');
    if (backButton) {
        backButton.onclick = () => {
            // Send back command via socket
            fetch('/ui-update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    returnToTabs: true
                })
            });
        };
    }

    // Add click handlers for items
    document.querySelectorAll('.library-item:not(.back-button)').forEach((item, index) => {
        item.onclick = () => {
            const uri = item.dataset.uri;
            if (!uri) return;

            document.querySelectorAll('.library-item').forEach(i => {
                i.classList.remove('selected');
                i.classList.remove('highlighted');
            });

            item.classList.add('selected');

            fetch('/play-context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ uri })
            }).catch(error => {
                console.error('Play error:', error);
            });
        };
    });
}

// Pagination handlers
document.getElementById('nextPage').onclick = () => {
    currentPage++;
    loadLibraryContent(
        currentTab === 'songs' ? 'liked-songs' : currentTab,
        currentPage * itemsPerPage
    );
};

document.getElementById('prevPage').onclick = () => {
    if (currentPage > 0) {
        currentPage--;
        loadLibraryContent(
            currentTab === 'songs' ? 'liked-songs' : currentTab,
            currentPage * itemsPerPage
        );
    }
};


// Add to your index.html socket.io handler
socket.on('ui-update', function (data) {
    if (data.focus_change) {
        // Define our navigation groups
        const tabElements = Array.from(document.querySelectorAll('.tab-btn'));
        const libraryElements = Array.from(document.querySelectorAll('.library-item, #prevPage, #nextPage'))
            .filter(el => !el.disabled && el.offsetParent !== null);

        // Determine which group we're currently in
        const activeElement = document.activeElement;
        const inTabGroup = tabElements.includes(activeElement);
        const inLibraryGroup = libraryElements.includes(activeElement);

        // Handle navigation based on current group
        if (inTabGroup) {
            // We're in the tabs section
            const currentIndex = tabElements.indexOf(activeElement);
            let nextIndex;

            if (data.focus_change === 'next') {
                if (currentIndex === tabElements.length - 1) {
                    // Last tab, moving next - jump to first library item
                    tabElements.forEach(el => el.classList.remove('highlighted'));
                    if (libraryElements.length > 0) {
                        libraryElements[0].focus();
                        libraryElements[0].classList.add('highlighted');
                    }
                    return;
                } else {
                    // Move to next tab
                    nextIndex = currentIndex + 1;
                }
            } else {
                // Move to previous tab or wrap around
                nextIndex = currentIndex - 1 < 0 ? tabElements.length - 1 : currentIndex - 1;
            }

            // Apply focus to next tab
            tabElements.forEach(el => el.classList.remove('highlighted'));
            tabElements[nextIndex].focus();
            tabElements[nextIndex].classList.add('highlighted');

        } else if (inLibraryGroup) {
            // We're in the library section
            const currentIndex = libraryElements.indexOf(activeElement);
            let nextIndex;

            if (data.focus_change === 'next') {
                nextIndex = currentIndex + 1 >= libraryElements.length ? 0 : currentIndex + 1;
            } else {
                if (currentIndex === 0) {
                    // First library item, moving previous - jump to tabs
                    libraryElements.forEach(el => el.classList.remove('highlighted'));
                    // Focus on active tab
                    const activeTab = document.querySelector('.tab-btn.active');
                    if (activeTab) {
                        activeTab.focus();
                        activeTab.classList.add('highlighted');
                    } else if (tabElements.length > 0) {
                        // Fallback to last tab
                        tabElements[tabElements.length - 1].focus();
                        tabElements[tabElements[tabElements.length - 1].classList.add('highlighted')];
                    }
                    return;
                } else {
                    nextIndex = currentIndex - 1;
                }
            }

            // Apply focus to next library item
            libraryElements.forEach(el => el.classList.remove('highlighted'));
            libraryElements[nextIndex].focus();
            libraryElements[nextIndex].classList.add('highlighted');

        } else {
            // Not in any group, set focus to active tab
            const activeTab = document.querySelector('.tab-btn.active');
            if (activeTab) {
                activeTab.focus();
                activeTab.classList.add('highlighted');
            }
        }
    } else if (data.trigger_click) {
        // Simulate click on focused element
        const activeElement = document.activeElement;
        
        // Check if we're clicking on a tab
        if (activeElement && activeElement.classList.contains('tab-btn')) {
            // Handle tab click with special logic
            activeElement.click();
            
            // Wait for content to load, then focus on the first library item
            setTimeout(() => {
                const firstLibraryItem = document.querySelector('.library-item');
                if (firstLibraryItem) {
                    document.querySelectorAll('.highlighted').forEach(el => {
                        el.classList.remove('highlighted');
                    });
                    firstLibraryItem.focus();
                    firstLibraryItem.classList.add('highlighted');
                }
            }, 1000); // Give enough time for content to load
        } else {
            // Normal click for other elements
            activeElement.click();
        }
    } else if (data.returnToTabs) {
        // Handle return to tabs - existing code works fine
        const activeTab = document.querySelector('.tab-btn.active');
        if (activeTab) {
            document.querySelectorAll('.highlighted').forEach(el => {
                el.classList.remove('highlighted');
            });
            activeTab.focus();
            activeTab.classList.add('highlighted');
        }
    } else if (data.tab !== undefined) {
        // When a tab is explicitly selected via index
        const tabs = document.querySelectorAll('.tab-btn');
        if (tabs[data.tab]) {
            tabs[data.tab].click();
            
            // Use a more reliable approach with multiple attempts
            let attempts = 0;
            const maxAttempts = 10;
            const checkForLibraryItems = () => {
                const firstItem = document.querySelector('.library-item');
                if (firstItem) {
                    document.querySelectorAll('.highlighted').forEach(el => {
                        el.classList.remove('highlighted');
                    });
                    firstItem.focus();
                    firstItem.classList.add('highlighted');
                    console.log('Successfully focused on first library item');
                } else if (attempts < maxAttempts) {
                    attempts++;
                    setTimeout(checkForLibraryItems, 300);
                    console.log('Waiting for library items to load, attempt:', attempts);
                }
            };
            
            // Start checking after a delay to allow the click to register
            setTimeout(checkForLibraryItems, 500);
        }
    } else if (data.item !== undefined) {
        // When an item is selected from the library - existing code works fine
        const items = document.querySelectorAll('.library-item');
        if (items[data.item]) {
            document.querySelectorAll('.highlighted').forEach(el => {
                el.classList.remove('highlighted');
            });
            items[data.item].focus();
            items[data.item].classList.add('highlighted');
            items[data.item].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }
});