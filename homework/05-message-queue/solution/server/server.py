from flask import Flask, request
from typing import List, Optional


class Server:
    # TODO: Implement API server
    def __init__(self, mq_host, mq_port, data_dir):
        pass

    def add_image(self, image_url: str) -> str:
        raise NotImplementedError

    def get_processed_images(self) -> List[str]:
        raise NotImplementedError

    def get_image_caption(self, image_id: str) -> Optional[str]:
        raise NotImplementedError


def create_app() -> Flask:
    app = Flask(__name__)

    server = Server('rabbitmq', 5672, '/data')

    @app.route('/api/v1.0/images', methods=['POST'])
    def add_image():
        body = request.get_json(force=True)
        image_id = server.add_image(body['image_url'])
        return {"image_id": image_id}

    @app.route('/api/v1.0/images', methods=['GET'])
    def get_processed_images():
        image_ids = server.get_processed_images()
        return {"image_ids": image_ids}

    @app.route('/api/v1.0/images/<string:image_id>', methods=['GET'])
    def get_image_caption(image_id):
        result = server.get_image_caption(image_id)
        if result is None:
            return "Image not found.", 404
        else:
            return {'caption': result}

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000)
