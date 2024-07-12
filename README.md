# Rocket League Bot Training Module

This project is a training module designed to help develop and train bots for Rocket League using the RLBot framework. It includes exercises, graders, and utilities to simulate various game scenarios and evaluate bot performance.

## Technologies Used

- **Python**: The primary programming language used for scripting the training exercises and bot logic.
- **RLBot Framework**: An open-source framework that facilitates the creation of bots for Rocket League. It provides the necessary tools and APIs for bot control and game state analysis.
- **Virtual Environment**: Recommended for managing Python dependencies specific to this project. Dependencies are listed in `requirements.txt`.

## Features

- **Drive to Ball Exercise**: A training exercise that evaluates a bot's ability to navigate to the ball on the field.
- **Grading System**: Utilizes graders to assess bot performance based on specific criteria, such as time taken to reach the ball and maintaining a certain distance.
- **Utility Scripts**: Includes various utility scripts such as `boost_pad_tracker.py` and `ball_prediction_analysis.py` to assist in bot training and development.

## Getting Started

1. Clone this repository to your local machine.
2. Ensure Python 3.7 or higher is installed.
3. Set up a virtual environment and activate it:

    ```sh
    python -m venv venv
    .\venv\Scripts\activate
    ```

4. Install the required dependencies:

    ```sh
    pip install -r requirements.txt
    ```

5. Run the training module:

    ```sh
    python run.py
    ```

For more detailed instructions and documentation, refer to the official RLBot documentation and the comments within the codebase.

- Bot behavior is controlled by `src/bot.py`
- Bot appearance is controlled by `src/appearance.cfg`

## Contributing

Contributions to the training module are welcome. Please read the `CONTRIBUTING.md` file for guidelines on how to contribute.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.
