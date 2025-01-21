require('dotenv').config();
const express = require('express');
const SpotifyWebApi = require('spotify-web-api-node');
const path = require('path');

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
  'app-remote-control'
];

const spotifyApi = new SpotifyWebApi({
    clientId: process.env.SPOTIFY_CLIENT_ID,
    clientSecret: process.env.SPOTIFY_CLIENT_SECRET,
    redirectUri: 'http://localhost:8888/callback'  // Changed from 3000 to 8888
});

let deviceId = null;
let isActive = false;

app.get('/login', (_, res) => {
    const authorizeURL = spotifyApi.createAuthorizeURL(SCOPES, 'state-token');
    res.redirect(authorizeURL);
});

app.get('/callback', async (req, res) => {
    const { code } = req.query;
    try {
        const data = await spotifyApi.authorizationCodeGrant(code);
        spotifyApi.setAccessToken(data.body.access_token);
        spotifyApi.setRefreshToken(data.body.refresh_token);
        
        // Inject token into player page
        res.redirect(`/?token=${data.body.access_token}`);
    } catch (err) {
        console.error('Auth error:', err);
        res.redirect('/login');
    }
});

app.post('/register-device', async (req, res) => {
    try {
        deviceId = req.body.device_id;
        console.log('Device registered:', deviceId);
        
        // Transfer playback to this device
        await spotifyApi.transferMyPlayback([deviceId], {
            play: false // Don't auto-play until requested
        });
        
        isActive = true;
        res.json({ success: true });
    } catch (error) {
        console.error('Failed to transfer playback:', error);
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

// Add error handler
app.use((error, req, res, next) => {
    console.error('Error:', error);
    res.status(500).json({ error: error.message });
});

const PORT = process.env.PORT || 8888;
app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log('Visit http://localhost:8888/login to start');
});