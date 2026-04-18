"""
CrowdLSTM — Real crowd density prediction model.

Architecture:
  - Bidirectional LSTM captures both rising and falling density trends
  - Multi-head self-attention over the temporal window
  - Two output heads: density regression + risk classification

Input:  (batch, seq_len=30, features=6)
  features: [density, entry_delta, exit_delta, velocity, hour_sin, hour_cos]

Outputs:
  - density_pred:   (batch, 5) — predicted density for next 5 ticks (each ~10s)
  - risk_logits:    (batch, 4) — logits for [low, medium, high, critical]
"""

import torch
import torch.nn as nn
import numpy as np


# ─────────────────────────────────────────────
#  Feature dimensions
# ─────────────────────────────────────────────
INPUT_FEATURES = 6          # per-zone feature vector length
SEQ_LEN = 30                # 30 ticks × 10 s = 5-minute lookback
HIDDEN_SIZE = 64
NUM_LAYERS = 2
ATTN_HEADS = 4
FORECAST_HORIZON = 5        # predict next 5 ticks → 50 s ahead
NUM_RISK_CLASSES = 4        # low / medium / high / critical


class TemporalAttention(nn.Module):
    """Scaled dot-product multi-head attention over time dimension."""

    def __init__(self, hidden: int, heads: int):
        super().__init__()
        self.attn = nn.MultiheadAttention(
            embed_dim=hidden * 2,   # bidirectional → 2×hidden
            num_heads=heads,
            batch_first=True,
            dropout=0.1,
        )
        self.norm = nn.LayerNorm(hidden * 2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        attn_out, _ = self.attn(x, x, x)
        return self.norm(x + attn_out)


class CrowdLSTM(nn.Module):
    """
    Bidirectional LSTM + Temporal Attention for crowd density forecasting.
    Predicts next-N density values AND risk level simultaneously.
    """

    def __init__(
        self,
        input_size: int = INPUT_FEATURES,
        hidden_size: int = HIDDEN_SIZE,
        num_layers: int = NUM_LAYERS,
        attn_heads: int = ATTN_HEADS,
        forecast_horizon: int = FORECAST_HORIZON,
        num_risk_classes: int = NUM_RISK_CLASSES,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.hidden_size = hidden_size
        self.forecast_horizon = forecast_horizon

        # Input projection
        self.input_proj = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.GELU(),
        )

        # Bidirectional LSTM
        self.lstm = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        # Temporal attention over all time steps
        self.attention = TemporalAttention(hidden_size, attn_heads)

        # Shared representation after pooling
        shared_dim = hidden_size * 2
        self.shared_head = nn.Sequential(
            nn.Linear(shared_dim, 128),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(128, 64),
            nn.GELU(),
        )

        # Density regression head (next N ticks, clamped to [0, 100])
        self.density_head = nn.Linear(64, forecast_horizon)

        # Risk classification head
        self.risk_head = nn.Sequential(
            nn.Linear(64, 32),
            nn.GELU(),
            nn.Linear(32, num_risk_classes),
        )

    def forward(self, x: torch.Tensor):
        """
        Args:
            x: (batch, seq_len, input_features)
        Returns:
            density_pred: (batch, forecast_horizon)   — values in [0, 100]
            risk_logits:  (batch, num_risk_classes)
        """
        projected = self.input_proj(x)           # (B, T, hidden)
        lstm_out, _ = self.lstm(projected)       # (B, T, 2*hidden)
        attended = self.attention(lstm_out)      # (B, T, 2*hidden)

        # Mean-pool over time to get fixed-size representation
        pooled = attended.mean(dim=1)            # (B, 2*hidden)

        shared = self.shared_head(pooled)        # (B, 64)
        density_pred = torch.sigmoid(self.density_head(shared)) * 100.0  # [0, 100]
        risk_logits = self.risk_head(shared)     # raw logits

        return density_pred, risk_logits


# ─────────────────────────────────────────────
#  Synthetic data generation (realistic patterns)
# ─────────────────────────────────────────────

def generate_event_timeline(duration_ticks: int = 1440) -> np.ndarray:
    """
    Simulate a realistic stadium event day.

    Timeline (ticks at 10s each → 1440 ticks = 4 hours):
      0–360:   Gates open, pre-event crowd build
      360–540: Near-capacity, peak entry
      540–720: Event in progress (stable high density)
      720–900: Halftime surge (food courts, restrooms)
      900–1080: Second half
      1080–1440: Post-event egress (critical density at exits)
    """
    t = np.linspace(0, 4 * np.pi, duration_ticks)
    hour_of_day = 17.0 + np.linspace(0, 4, duration_ticks)

    # Base crowd curve: logistic rise → plateau → logistic fall
    entry_phase = 1 / (1 + np.exp(-0.015 * (np.arange(duration_ticks) - 350)))
    exit_phase = 1 / (1 + np.exp(0.02 * (np.arange(duration_ticks) - 1150)))
    base_density = entry_phase * exit_phase * 85 + 5

    # Halftime spike
    halftime = 15 * np.exp(-0.5 * ((np.arange(duration_ticks) - 720) / 30) ** 2)

    # Micro-fluctuations (people moving between zones)
    noise = np.random.normal(0, 2.5, duration_ticks)

    density = np.clip(base_density + halftime + noise, 0, 100)

    # Entry / exit deltas (finite difference)
    entry_delta = np.clip(np.diff(density, prepend=density[0]) * 0.5, 0, 20)
    exit_delta = np.clip(-np.diff(density, prepend=density[0]) * 0.5, 0, 20)

    # Velocity: inversely related to density (crushes slow people down)
    velocity = np.clip(2.0 - density / 70.0, 0.2, 2.0) + np.random.normal(0, 0.1, duration_ticks)

    # Cyclical time encoding
    hour_rad = (hour_of_day % 24) / 24.0 * 2 * np.pi
    hour_sin = np.sin(hour_rad)
    hour_cos = np.cos(hour_rad)

    # Stack: (duration_ticks, 6)
    return np.stack([density, entry_delta, exit_delta, velocity, hour_sin, hour_cos], axis=1)


def build_dataset(
    num_events: int = 200,
    seq_len: int = SEQ_LEN,
    horizon: int = FORECAST_HORIZON,
):
    """
    Generate (X, y_density, y_risk) training tensors from synthetic event simulations.

    y_risk labels:
      0 = low    (density < 40)
      1 = medium (density < 60)
      2 = high   (density < 80)
      3 = critical
    """
    Xs, yd_list, yr_list = [], [], []

    for _ in range(num_events):
        timeline = generate_event_timeline()
        T = len(timeline)

        for start in range(0, T - seq_len - horizon, 5):  # stride=5 for variety
            window = timeline[start: start + seq_len]              # (seq_len, 6)
            future_density = timeline[start + seq_len: start + seq_len + horizon, 0]  # (horizon,)

            peak_future = future_density.max()
            if peak_future < 40:
                risk_label = 0
            elif peak_future < 60:
                risk_label = 1
            elif peak_future < 80:
                risk_label = 2
            else:
                risk_label = 3

            Xs.append(window)
            yd_list.append(future_density)
            yr_list.append(risk_label)

    X = torch.tensor(np.array(Xs), dtype=torch.float32)
    y_density = torch.tensor(np.array(yd_list), dtype=torch.float32)
    y_risk = torch.tensor(np.array(yr_list), dtype=torch.long)

    return X, y_density, y_risk


# ─────────────────────────────────────────────
#  Training helpers
# ─────────────────────────────────────────────

def train_model(
    model: CrowdLSTM,
    X: torch.Tensor,
    y_density: torch.Tensor,
    y_risk: torch.Tensor,
    epochs: int = 30,
    batch_size: int = 256,
    lr: float = 3e-4,
    device: str = "cpu",
) -> list:
    """Train the model and return per-epoch loss history."""
    model = model.to(device)
    X, y_density, y_risk = X.to(device), y_density.to(device), y_risk.to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    density_loss_fn = nn.HuberLoss(delta=5.0)
    risk_loss_fn = nn.CrossEntropyLoss()

    n = X.shape[0]
    losses = []

    model.train()
    for epoch in range(epochs):
        perm = torch.randperm(n, device=device)
        epoch_loss = 0.0
        batches = 0

        for i in range(0, n, batch_size):
            idx = perm[i: i + batch_size]
            xb, ydb, yrb = X[idx], y_density[idx], y_risk[idx]

            pred_density, risk_logits = model(xb)
            loss_d = density_loss_fn(pred_density, ydb)
            loss_r = risk_loss_fn(risk_logits, yrb)
            loss = loss_d + 0.3 * loss_r   # combined objective

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            epoch_loss += loss.item()
            batches += 1

        scheduler.step()
        avg = epoch_loss / batches
        losses.append(avg)
        print(f"Epoch {epoch + 1:3d}/{epochs}  loss={avg:.4f}  lr={scheduler.get_last_lr()[0]:.2e}")

    return losses


def save_model(model: CrowdLSTM, path: str = "crowd_lstm.pt"):
    torch.save({
        "state_dict": model.state_dict(),
        "config": {
            "input_size": INPUT_FEATURES,
            "hidden_size": model.hidden_size,
            "forecast_horizon": model.forecast_horizon,
        }
    }, path)
    print(f"Model saved → {path}")


def load_model(path: str = "crowd_lstm.pt") -> CrowdLSTM:
    checkpoint = torch.load(path, map_location="cpu")
    cfg = checkpoint["config"]
    model = CrowdLSTM(
        input_size=cfg["input_size"],
        hidden_size=cfg["hidden_size"],
        forecast_horizon=cfg["forecast_horizon"],
    )
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model


# ─────────────────────────────────────────────
#  Quick-start entrypoint
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("Building dataset …")
    X, y_density, y_risk = build_dataset(num_events=100)
    print(f"  X: {X.shape}  y_density: {y_density.shape}  y_risk: {y_risk.shape}")

    model = CrowdLSTM()
    print(f"  Parameters: {sum(p.numel() for p in model.parameters()):,}")

    train_model(model, X, y_density, y_risk, epochs=30, batch_size=256)
    save_model(model, "crowd_lstm.pt")

    # Smoke-test inference
    model.eval()
    with torch.no_grad():
        sample = X[:1]
        d, r = model(sample)
        risk_names = ["low", "medium", "high", "critical"]
        print(f"\nSample inference:")
        print(f"  Density forecast (next 50s): {d[0].numpy().round(1)}")
        print(f"  Risk class: {risk_names[r[0].argmax().item()]}")
