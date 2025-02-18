document.getElementById('playPauseBtn').onclick = () => {
    fetch('/play', { method: 'POST' });
};

document.getElementById('prevBtn').onclick = () => {
    fetch('/previous', { method: 'POST' });
};

document.getElementById('nextBtn').onclick = () => {
    fetch('/next', { method: 'POST' });
};

// Update UI with player state
function updatePlayerState(state) {
    if (!state) return;

    const track = state.track_window.current_track;
    document.getElementById('trackName').textContent = track.name;
    document.getElementById('artistName').textContent = track.artists[0].name;
    document.getElementById('albumArt').src = track.album.images[0].url;
    document.getElementById('playPauseBtn').textContent = state.paused ? 'Play' : 'Pause';
}

// Poll for player state
setInterval(() => {
    fetch('/player-state')
        .then(res => res.json())
        .then(updatePlayerState)
        .catch(console.error);
}, 1000);