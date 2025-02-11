const { QMainWindow, QWidget, QLabel, QPushButton, QBoxLayout, FlexLayout, QPixmap } = require("@nodegui/nodegui");

class SpotifyPlayerWindow extends QMainWindow {
  constructor(spotifyApi) {
    super();
    this.spotifyApi = spotifyApi;
    this.setupUi();
  }

  setupUi() {
    this.setWindowTitle("W/AV Player");
    this.resize(800, 480); // Common Raspberry Pi display resolution

    // Create central widget and layout
    const centralWidget = new QWidget();
    const rootLayout = new FlexLayout();
    centralWidget.setLayout(rootLayout);

    // Status display
    this.statusLabel = new QLabel();
    this.statusLabel.setText("Initializing...");

    // Now Playing section
    this.albumArt = new QLabel();
    this.albumArt.setFixedSize(300, 300);
    
    this.trackInfo = new QLabel("Not Playing");
    this.trackInfo.setStyleSheet("font-size: 24px;");

    // Controls
    const controlsWidget = new QWidget();
    const controlsLayout = new QBoxLayout(2); // Horizontal
    controlsWidget.setLayout(controlsLayout);

    this.prevButton = new QPushButton("Previous");
    this.playPauseButton = new QPushButton("Play");
    this.nextButton = new QPushButton("Next");

    controlsLayout.addWidget(this.prevButton);
    controlsLayout.addWidget(this.playPauseButton);
    controlsLayout.addWidget(this.nextButton);

    // Add widgets to root layout
    rootLayout.addWidget(this.statusLabel);
    rootLayout.addWidget(this.albumArt);
    rootLayout.addWidget(this.trackInfo);
    rootLayout.addWidget(controlsWidget);

    this.setCentralWidget(centralWidget);

    this.setupHandlers();
  }

  setupHandlers() {
    this.playPauseButton.addEventListener('clicked', () => {
      this.spotifyApi.play();
    });

    this.prevButton.addEventListener('clicked', () => {
      this.spotifyApi.previousTrack();
    });

    this.nextButton.addEventListener('clicked', () => {
      this.spotifyApi.nextTrack();
    });
  }

  updateStatus(status) {
    this.statusLabel.setText(status);
  }

  updateNowPlaying(track) {
    this.trackInfo.setText(`${track.name}\n${track.artists[0].name}`);
    // Update album art
    if (track.album.images[0]) {
      fetch(track.album.images[0].url)
        .then(response => response.arrayBuffer())
        .then(buffer => {
          const pixmap = new QPixmap();
          pixmap.loadFromData(Buffer.from(buffer));
          this.albumArt.setPixmap(pixmap);
        });
    }
  }

  setPlaybackState(isPlaying) {
    this.playPauseButton.setText(isPlaying ? "Pause" : "Play");
  }
}

module.exports = { SpotifyPlayerWindow };