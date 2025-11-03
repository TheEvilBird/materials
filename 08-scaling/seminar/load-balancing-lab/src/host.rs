use std::cell::RefCell;
use std::collections::VecDeque;
use std::rc::Rc;

use simcore::cast;
use simcore::context::SimulationContext;
use simcore::event::Event;
use simcore::handler::EventHandler;

use crate::events::RequestEndEvent;
use crate::log::EventLog;

pub struct Host {
    #[allow(dead_code)]
    pub id: usize,
    pub requests: VecDeque<(f64, f64)>,
    slowdown: f64,
    log: Rc<RefCell<EventLog>>,
    ctx: Rc<RefCell<SimulationContext>>,
}

impl Host {
    pub fn new(
        id: usize,
        slowdown: f64,
        log: Rc<RefCell<EventLog>>,
        ctx: Rc<RefCell<SimulationContext>>,
    ) -> Self {
        Self {
            id,
            requests: Default::default(),
            slowdown,
            log,
            ctx,
        }
    }

    pub fn on_new_request(&mut self, duration: f64, time: f64) {
        self.requests.push_back((duration * self.slowdown, time));
        if self.requests.len() == 1 {
            self.ctx
                .borrow_mut()
                .emit_self(RequestEndEvent {}, duration * self.slowdown);
        }
    }

    // executed on simulation end
    pub fn flush(&mut self, time: f64) {
        let mut log = self.log.borrow_mut();
        for &(_, old) in self.requests.iter() {
            log.push((time, old));
        }
    }
}

impl EventHandler for Host {
    fn on(&mut self, event: Event) {
        cast!(match event.data {
            RequestEndEvent {} => {
                let (_, old) = self.requests.pop_front().unwrap();
                self.log.borrow_mut().push((event.time, old));
                if let Some((delay, _)) = self.requests.front() {
                    self.ctx.borrow_mut().emit_self(RequestEndEvent {}, *delay);
                }
            }
        });
    }
}
