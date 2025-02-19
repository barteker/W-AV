require('dotenv').config();
const express = require('express');
const SpotifyWebApi = require('spotify-web-api-node');
const path = require('path');
const fs = require('fs');


const app = express();
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
        await spotifyApi.play({
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

// Update the play-context route to handle both contexts and individual tracks
app.post('/play-context', async (req, res) => {
    try {
        const { uri, offset = 0 } = req.body;
        
        // If it's a track URI (liked songs), play directly
        if (uri.startsWith('spotify:track:')) {
            await spotifyApi.play({
                device_id: deviceId,
                uris: [uri]
            });
        } else {
            // For playlists and albums, play as context
            await spotifyApi.play({
                device_id: deviceId,
                context_uri: uri,
                offset: { position: offset }
            });
        }
        
        res.json({ success: true });
    } catch (error) {
        console.error('Play error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Add error handler
app.use((error, req, res, next) => {
    console.error('Error:', error);
    res.status(500).json({ error: error.message });
});

const PORT = process.env.PORT || 8888;
app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
});