from model import CrowdLSTM, build_dataset, train_model, save_model


def main():
    print("Building synthetic dataset for bundled checkpoint...")
    X, y_density, y_risk = build_dataset(num_events=60)
    model = CrowdLSTM()
    train_model(model, X, y_density, y_risk, epochs=10, batch_size=256)
    save_model(model, "crowd_lstm.pt")


if __name__ == "__main__":
    main()
