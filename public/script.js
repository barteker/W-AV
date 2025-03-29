const statusEl = document.getElementById('status');
const params = new URLSearchParams(window.location.search);
const token = params.get('token');

// creates global storage for focusable elements
let cachedFocusableElements = [];
let lastFocusableUpdate = 0;

if (!token) {
    statusEl.textContent = 'No token found, redirecting...';
    window.location.href = '/auto-login';
} else {
    statusEl.textContent = 'Token found, initializing player...';
}

// Move socket initialization outside of onSpotifyWebPlaybackSDKReady
const socket = io();

// At the top of your script.js file, add this line
let player; // Define player globally

window.onSpotifyWebPlaybackSDKReady = () => {
    statusEl.textContent = 'SDK Ready, creating player...';

    player = new Spotify.Player({ // Remove 'const' here
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
                    // Hide the status element completely once device is registered
                    statusEl.style.display = 'none';
                    
                    // Add class to body to adjust layout
                    document.body.classList.add('status-hidden');
                    
                    // Enable control buttons
                    document.getElementById('prevBtn').disabled = false;
                    document.getElementById('playPauseBtn').disabled = false;
                    document.getElementById('nextBtn').disabled = false;

                    initializePlayerState();
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
            // Update global playback state
            window.playerState = {
                isPlaying: !state.paused,
                currentUri: state.context ? state.context.uri : 
                           (state.track_window.current_track ? state.track_window.current_track.uri : null),
                deviceReady: true,
                trackProgress: state.position,
                trackDuration: state.duration
            };
            
            // Update Now Playing UI
            updateNowPlayingUI(state);
            
            // Update play/pause button
            document.getElementById('playPauseBtn').textContent = 
                state.paused ? 'Play' : 'Pause';
                
            console.log('Playback state updated:', window.playerState);
            
            // Start progress tracking if playing
            if (!state.paused) {
                startProgressTracking();
            }
        }
    });

    // Control buttons
    document.getElementById('playPauseBtn').onclick = () => {
        // Use the API endpoint instead of player.togglePlay()
        fetch('/play', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(response => response.json())
        .then(data => {
            console.log('Play/pause response:', data);
        })
        .catch(error => {
            console.error('Play/pause error:', error);
        });
    };

    document.getElementById('prevBtn').onclick = () => {
        fetch('/previous', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(response => response.json())
        .then(data => {
            console.log('Previous track response:', data);
        })
        .catch(error => {
            console.error('Previous track error:', error);
        });
    };

    document.getElementById('nextBtn').onclick = () => {
        fetch('/next', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(response => response.json())
        .then(data => {
            console.log('Next track response:', data);
        })
        .catch(error => {
            console.error('Next track error:', error);
        });
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

// File: /home/wave/W-AV/public/script.js

// 1. First, create a unified play function to be used by both UI clicks and rotary encoder
function playUri(uri) {
    // Update UI immediately for responsive feel
    document.getElementById('nowPlayingTrack').textContent = 'Loading...';
    document.getElementById('nowPlayingArtist').textContent = '';
    document.getElementById('progressFill').style.width = '0%';
    
    return fetch('/play-context', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uri })
    })
    .then(response => {
        if (!response.ok) throw new Error(`Playback request failed: ${response.status}`);
        return response.json();
    })
    .then(data => {
        console.log('Play response:', data);
        return data;
    });
}

// 2. Update the library-item click handler in renderLibraryItems() to use this function
function renderLibraryItems(items, tab) {
    const contentDiv = document.getElementById('library-content');
    
    // No more back button - just directly render library items
    let html = items.map((item, index) => {
        if (tab === 'albums') {
            const album = item.album;
            return `
                <div class="library-item" tabindex="0" data-uri="${album.uri}" data-index="${index}">
                    <img src="${album.images[0]?.url || 'default-cover.png'}" alt="Cover">
                    <div>
                        <div>${album.name}</div>
                        <div class="artist">${album.artists[0]?.name || 'Unknown Artist'}</div>
                    </div>
                </div>
            `;
        } else {
            return `
                <div class="library-item" tabindex="0" data-uri="${item.uri || item.track?.uri}" data-index="${index}">
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

    // Handle empty content case
    if (!html) {
        html = '<div class="no-items">No items found</div>';
    }

    contentDiv.innerHTML = html;

    // Add click handlers for items
    document.querySelectorAll('.library-item').forEach((item, index) => {
        // Ensure all items have tabindex
        if (item.getAttribute('tabindex') === null) {
            item.setAttribute('tabindex', '0');
        }
        
        item.onclick = () => {
            const uri = item.dataset.uri;
            if (!uri) return;

            document.querySelectorAll('.library-item').forEach(i => {
                i.classList.remove('selected');
                i.classList.remove('highlighted');
            });

            item.classList.add('selected');

            // Use the unified playUri function
            playUri(uri).catch(error => {
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
        const now = Date.now();
        
        // Only rebuild focusable elements cache every 500ms or when needed
        if (cachedFocusableElements.length === 0 || now - lastFocusableUpdate > 500) {
            // Set tabindex only on initial load
            document.querySelectorAll('.library-item').forEach((item, i) => {
                if (item.getAttribute('tabindex') === null) {
                    item.setAttribute('tabindex', '0');
                }
            });
            
            // Add tabindex to pagination buttons if needed
            ['#prevPage', '#nextPage'].forEach(id => {
                const element = document.querySelector(id);
                if (element && element.getAttribute('tabindex') === null) {
                    element.setAttribute('tabindex', '0');
                }
            });
            
            cachedFocusableElements = Array.from(document.querySelectorAll(
                '.tab-btn, [tabindex="0"], .library-item, #prevPage, #nextPage'
            )).filter(el => !el.disabled && el.offsetParent !== null);
            
            lastFocusableUpdate = now;
            console.log('Rebuilt focusable elements cache, count:', cachedFocusableElements.length);
        }
        
        // Find current position in focusable elements array
        const currentIndex = cachedFocusableElements.indexOf(document.activeElement);
        console.log('Current focus index:', currentIndex, 'Direction:', data.focus_change);
        
        // If nothing is focused yet, start with the first element
        let nextIndex;
        if (currentIndex === -1) {
            nextIndex = 0;
        } else {
            // Calculate next index based on direction
            if (data.focus_change === 'next') {
                nextIndex = (currentIndex + 1) % cachedFocusableElements.length;
            } else {
                nextIndex = (currentIndex - 1 + cachedFocusableElements.length) % cachedFocusableElements.length;
            }
        }
        
        // Remove highlight from all elements
        document.querySelectorAll('.highlighted').forEach(el => {
            el.classList.remove('highlighted');
        });
        
        // Focus and highlight the next element
        if (cachedFocusableElements[nextIndex]) {
            cachedFocusableElements[nextIndex].focus();
            cachedFocusableElements[nextIndex].classList.add('highlighted');
            
            // Ensure element is visible
            cachedFocusableElements[nextIndex].scrollIntoView({
                behavior: 'auto', // Changed from smooth to auto for better responsiveness
                block: 'nearest'
            });
            
            console.log('New focus:', nextIndex, cachedFocusableElements[nextIndex].textContent || cachedFocusableElements[nextIndex].className);
        }
    } else if (data.trigger_click) {
        const activeElement = document.activeElement;
        
        if (activeElement) {
            console.log('Triggering click on:', activeElement.tagName, activeElement.className);
            
            if (activeElement.classList.contains('tab-btn')) {
                // Tab button handling - no changes needed
                activeElement.click();
                
                // ...existing tab click code...
            } else if (activeElement.classList.contains('library-item')) {
                // Library item handling - use the unified play function
                const uri = activeElement.dataset.uri;
                
                if (uri) {
                    // Update UI
                    document.querySelectorAll('.library-item').forEach(i => {
                        i.classList.remove('selected');
                    });
                    
                    activeElement.classList.add('selected');
                    
                    // Use unified playUri function with UI updates after success
                    playUri(uri)
                        .then(data => {
                            // Update highlighting after successful play
                            if (data.success) {
                                document.querySelectorAll('.highlighted').forEach(el => {
                                    if (!el.classList.contains('selected')) {
                                        el.classList.remove('highlighted');
                                    }
                                });
                            }
                        })
                        .catch(error => {
                            console.error('Play error:', error);
                        });
                }
            } else if (activeElement.id === 'prevPage' || activeElement.id === 'nextPage') {
                // Pagination button handling - no changes
                activeElement.click();
            } else if (activeElement.id === 'playPauseBtn' || 
                       activeElement.id === 'prevBtn' || 
                       activeElement.id === 'nextBtn' || 
                       activeElement.id === 'logoutBtn') {
                // Control buttons - no changes
                activeElement.click();
            } else {
                // Standard click behavior - no changes
                activeElement.click();
            }
        }
    }
});

// Add these new functions

function formatTime(ms) {
    const minutes = Math.floor(ms / 60000);
    const seconds = Math.floor((ms % 60000) / 1000);
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function updateNowPlayingUI(state) {
    const track = state.track_window.current_track;
    if (!track) return;
    
    // Update track info
    document.getElementById('nowPlayingTrack').textContent = track.name;
    document.getElementById('nowPlayingArtist').textContent = track.artists.map(a => a.name).join(', ');
    
    // Update album art
    if (track.album && track.album.images && track.album.images.length > 0) {
        document.getElementById('nowPlayingArt').src = track.album.images[0].url;
    } else {
        document.getElementById('nowPlayingArt').src = 'default-cover.png';
    }
    
    // Update times
    document.getElementById('currentTime').textContent = formatTime(state.position);
    document.getElementById('totalTime').textContent = formatTime(state.duration);
    
    // Update progress bar
    const progressPercent = (state.position / state.duration) * 100;
    document.getElementById('progressFill').style.width = `${progressPercent}%`;
}

// Tracking playback progress
let progressInterval;

function startProgressTracking() {
    // Clear any existing interval
    if (progressInterval) {
        clearInterval(progressInterval);
    }
    
    // Start a new interval that updates every second
    let lastKnownPosition = window.playerState.trackProgress;
    const startTime = Date.now();
    
    progressInterval = setInterval(() => {
        if (!window.playerState.isPlaying) {
            clearInterval(progressInterval);
            return;
        }
        
        // Calculate current position based on elapsed time
        const elapsed = Date.now() - startTime;
        const estimatedPosition = lastKnownPosition + elapsed;
        
        if (estimatedPosition >= window.playerState.trackDuration) {
            clearInterval(progressInterval);
            return;
        }
        
        // Update UI
        document.getElementById('currentTime').textContent = formatTime(estimatedPosition);
        const progressPercent = (estimatedPosition / window.playerState.trackDuration) * 100;
        document.getElementById('progressFill').style.width = `${progressPercent}%`;
    }, 1000);
}

// Add this function to script.js to handle the initialization sequence
function initializePlayerState() {
    console.log('Initializing player state with simulated clicks...');
    
    // First, simulate a play button click
    return new Promise(resolve => {
        console.log('Simulating initial play click');
        document.getElementById('playPauseBtn').click();
        
        // Wait for the click to process
        setTimeout(() => {
            console.log('Waiting for play action to complete...');
            // Wait another second before pausing
            setTimeout(() => {
                console.log('Simulating pause click');
                // Simulate a second click to pause
                document.getElementById('playPauseBtn').click();
                
                // Allow time for pause to complete
                setTimeout(() => {
                    console.log('Player fully initialized and ready for GPIO control');
                    resolve();
                }, 500);
            }, 1000);
        }, 500);
    });
}

// Add this to bottom of script.js
socket.on('simulate-click', function(data) {
    console.log('Simulating click on button:', data.button);
    
    // Simulate the appropriate button click
    if (data.button === 'play') {
        document.getElementById('playPauseBtn').click();
    } else if (data.button === 'next') {
        document.getElementById('nextBtn').click();
    } else if (data.button === 'prev') {
        document.getElementById('prevBtn').click();
    }
});
