class Worker:
    # TODO: Implement server
    def __init__(self, mq_host, mq_port, data_dir):
        pass

    def produce_image_caption(self, image_url):
        return str(abs(hash(image_url)) % (10 ** 8))
    
    def run(self):
        raise NotImplementedError


if __name__ == '__main__':
    worker = Worker('rabbitmq', 5672, '/data')
    worker.run()
