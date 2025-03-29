require('dotenv').config();
const express = require('express');
const SpotifyWebApi = require('spotify-web-api-node');
const path = require('path');
const fs = require('fs');
const app = express();
const server = require('http').createServer(app);
const io = require('socket.io')(server);

// Add this line to define the port
const PORT = process.env.PORT || 8888;

app.use(express.json());
app.use(express.static('public'));

const SCOPES = [
  'streaming',
  'user-read-email',
  'user-read-private',
  'user-read-playback-state',
  'user-modify-playback-state',
  'user-read-currently-playing',
  'app-remote-control',
  'playlist-read-private',
  'playlist-read-collaborative',
  'user-library-read',
  'user-read-playback-position'
];

// checks if it's processing the client ID 
if (!process.env.SPOTIFY_CLIENT_ID || !process.env.SPOTIFY_CLIENT_SECRET) {
    console.error('Missing required Spotify credentials in .env file');
    process.exit(1);
}

const spotifyApi = new SpotifyWebApi({
    clientId: process.env.SPOTIFY_CLIENT_ID,
    clientSecret: process.env.SPOTIFY_CLIENT_SECRET,
    redirectUri: 'http://localhost:8888/callback'  
});

const TOKEN_PATH = path.join(__dirname, '.credentials');
const TOKEN_FILE = path.join(TOKEN_PATH, 'spotify_tokens.json');

const saveTokens = (tokens) => {
    if (!fs.existsSync(TOKEN_PATH)) {
        fs.mkdirSync(TOKEN_PATH, { recursive: true });
    }
    fs.writeFileSync(TOKEN_FILE, JSON.stringify(tokens));
};

const loadTokens = () => {
    try {
        return JSON.parse(fs.readFileSync(TOKEN_FILE));
    } catch {
        return null;
    }
};

let deviceId = null;
let isActive = false;

// Add this route handler near the top of your routes
app.get('/', (req, res) => {
    const tokens = loadTokens();
    if (!tokens) {
        res.redirect('/login');
        return;
    }
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Add this before the auto-login route
app.get('/login', (req, res) => {
    // Clear any existing tokens before showing login
    if (fs.existsSync(TOKEN_FILE)) {
        fs.unlinkSync(TOKEN_FILE);
    }
    // Reset API client state
    spotifyApi.setAccessToken(null);
    spotifyApi.setRefreshToken(null);
    deviceId = null;
    isActive = false;
    
    const authorizeURL = spotifyApi.createAuthorizeURL(SCOPES, 'state-token', true);
    res.redirect(authorizeURL);
});

app.get('/callback', async (req, res) => {
    const { code } = req.query;
    try {
        const data = await spotifyApi.authorizationCodeGrant(code);
        const tokens = {
            access_token: data.body.access_token,
            refresh_token: data.body.refresh_token,
            expires_at: Date.now() + (data.body.expires_in * 1000)
        };
        
        saveTokens(tokens);
        spotifyApi.setAccessToken(tokens.access_token);
        spotifyApi.setRefreshToken(tokens.refresh_token);
        
        res.redirect(`/?token=${tokens.access_token}`);
    } catch (err) {
        console.error('Auth error:', err);
        res.redirect('/login');
    }
});

// Add this near the other routes
app.post('/logout', (req, res) => {
    try {
        // Clear the stored tokens
        if (fs.existsSync(TOKEN_FILE)) {
            fs.unlinkSync(TOKEN_FILE);
        }
        // Reset API client state
        spotifyApi.setAccessToken(null);
        spotifyApi.setRefreshToken(null);
        // Reset device state
        deviceId = null;
        isActive = false;

        const authorizeURL = spotifyApi.createAuthorizeURL(SCOPES, 'state-token', true);
    res.redirect(authorizeURL);
    } catch (error) {
        console.error('Logout error:', error);
        res.redirect('/login');
    }
});

// Add this new route to handle post-Spotify logout
app.get('/post-logout', (req, res) => {
    res.redirect('/login');
});

app.get('/auto-login', async (req, res) => {
    const tokens = loadTokens();
    if (!tokens) {
        res.redirect('/login');
        return;
    }

    try {
        if (Date.now() > tokens.expires_at) {
            const data = await spotifyApi.refreshAccessToken();
            tokens.access_token = data.body.access_token;
            tokens.expires_at = Date.now() + (data.body.expires_in * 1000);
            saveTokens(tokens);
        }
        
        spotifyApi.setAccessToken(tokens.access_token);
        spotifyApi.setRefreshToken(tokens.refresh_token);
        res.redirect(`/?token=${tokens.access_token}`);
    } catch (err) {
        console.error('Auto-login failed:', err);
        res.redirect('/login');
    }
});

// Add this new route to check premium status
app.get('/check-premium', async (req, res) => {
    try {
        const me = await spotifyApi.getMe();
        const isPremium = me.body.product === 'premium';
        res.json({ isPremium });
    } catch (error) {
        console.error('Failed to check premium status:', error);
        res.status(500).json({ error: error.message });
    }
});

// Update the register-device route
app.post('/register-device', async (req, res) => {
    try {
        // Check premium status first
        const me = await spotifyApi.getMe();
        if (me.body.product !== 'premium') {
            throw new Error('Premium account required');
        }

        deviceId = req.body.device_id;
        console.log('Device registered:', deviceId);
        
        // Transfer playback to this device
        await spotifyApi.transferMyPlayback([deviceId], {
            play: false
        });
        
        isActive = true;
        res.json({ success: true });
    } catch (error) {
        console.error('Failed to register device:', error);
        res.status(500).json({ error: error.message });
    }
});

app.post('/play', async (req, res) => {
    try {
        if (!isActive || !deviceId) {
            throw new Error('Device not ready');
        }
        const state = await spotifyApi.getMyCurrentPlaybackState();
        if (state.body && state.body.is_playing) {
            await spotifyApi.pause({
                device_id: deviceId
            });
        } else {
            await spotifyApi.play({
                device_id: deviceId
            });
        }
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/stop', async (req, res) => {
    try {
        if (!isActive || !deviceId) {
            throw new Error('Device not ready');
        }
        await spotifyApi.pause({
            device_id: deviceId
        });
        // Seek to beginning of track
        await spotifyApi.seek(0, {
            device_id: deviceId
        });
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/pause', async (req, res) => {
    try {
        if (!isActive || !deviceId) {
            throw new Error('Device not ready');
        }
        await spotifyApi.pause({
            device_id: deviceId
        });
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/refresh_token', async (req, res) => {
    try {
        const data = await spotifyApi.refreshAccessToken();
        spotifyApi.setAccessToken(data.body.access_token);
        res.json({ access_token: data.body.access_token });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});


// Add this route for the player state
app.get('/player-state', async (req, res) => {
    try {
        const state = await spotifyApi.getMyCurrentPlaybackState();
        res.json(state.body);
    } catch (error) {
        console.error('Error getting playback state:', error);
        res.status(500).json({ error: error.message });
    }
});

// Add these missing routes for previous/next
app.post('/previous', async (req, res) => {
    try {
        await spotifyApi.skipToPrevious();
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/next', async (req, res) => {
    try {
        await spotifyApi.skipToNext();
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Add these new routes for library access
app.get('/playlists', async (req, res) => {
    try {
        const data = await spotifyApi.getUserPlaylists();
        res.json(data.body.items);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/albums', async (req, res) => {
    try {
        const data = await spotifyApi.getMySavedAlbums();
        res.json(data.body.items);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/liked-songs', async (req, res) => {
    try {
        const data = await spotifyApi.getMySavedTracks();
        res.json(data.body.items);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Optimize play-context route
app.post('/play-context', async (req, res) => {
    try {
        const { uri, offset = 0 } = req.body;
        
        if (!uri || !deviceId) {
            throw new Error(uri ? 'No active device' : 'URI is required');
        }
        
        // Track if we've sent a response to avoid double-sending
        let responseSent = false;
        
        // Send response early for better UI responsiveness
        const sendResponse = () => {
            if (!responseSent) {
                responseSent = true;
                res.json({ success: true });
            }
        };
        
        // Only transfer playback if device isn't already active
        if (!isActive) {
            await spotifyApi.transferMyPlayback([deviceId], { play: false });
            await new Promise(resolve => setTimeout(resolve, 100)); // Reduced from 300ms
            isActive = true;
        }
        
        // Send the play command right away without checking state
        try {
            if (uri.startsWith('spotify:track:')) {
                await spotifyApi.play({
                    device_id: deviceId,
                    uris: [uri]
                });
            } else {
                await spotifyApi.play({
                    device_id: deviceId,
                    context_uri: uri,
                    offset: { position: offset }
                });
            }
            
            // Send response as soon as play command succeeds
            sendResponse();
            
        } catch (error) {
            // Fall back to recovery code
            if (error.message.includes('Player command failed')) {
                await spotifyApi.transferMyPlayback([deviceId], { play: true });
                
                // Shorter delay
                await new Promise(resolve => setTimeout(resolve, 200)); // Reduced from 500ms
                
                // Retry play command
                // [Play commands]
                
                sendResponse();
            } else {
                throw error;
            }
        }
    } catch (error) {
        console.error('Play error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Add these new routes for pagination and display updates
app.get('/:type', async (req, res) => {
    const { type } = req.params;
    const offset = parseInt(req.query.offset) || 0;
    const limit = parseInt(req.query.limit) || 20;

    try {
        let data;
        switch(type) {
            case 'playlists':
                data = await spotifyApi.getUserPlaylists({ limit, offset });
                break;
            case 'albums':
                data = await spotifyApi.getMySavedAlbums({ limit, offset });
                break;
            case 'liked-songs':
                data = await spotifyApi.getMySavedTracks({ limit, offset });
                break;
            default:
                throw new Error('Invalid type');
        }
        module.exports = data;
        res.json(data.body.items);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/update-display', (req, res) => {
    // This will be used by the WebSocket connection
    const { current_tab, current_item, items } = req.body;
    // Broadcast to connected clients
    io.emit('display-update', { current_tab, current_item, items });
    res.json({ success: true });
});

// Update the existing ui-update route
app.post('/ui-update', (req, res) => {
    try {
        const { tab, item, returnToTabs, focus_change, trigger_click } = req.body;
        
        // Emit the update to all connected clients
        io.emit('ui-update', { 
            tab, 
            item,
            returnToTabs,
            focus_change,
            trigger_click
        });
        
        res.json({ success: true });
    } catch (error) {
        console.error('UI update error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Add this new endpoint to simulate UI clicks
app.post('/simulate-click', (req, res) => {
    const { button } = req.body; // 'play', 'next', 'prev'
    
    // Broadcast a click simulation event to all connected clients
    io.emit('simulate-click', { button });
    res.json({ success: true });
});

// Add error handler
app.use((error, req, res, next) => {
    console.error('Error:', error);
    res.status(500).json({ error: error.message });
});



// Update your existing server.listen to use the http server
server.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
});