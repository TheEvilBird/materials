use std::cell::RefCell;
use std::cmp::Ordering;
use std::collections::BTreeSet;
use std::fs::File;
use std::io::prelude::*;
use std::io::BufWriter;
use std::path::Path;
use std::rc::Rc;

use clap::Parser;
use rand::prelude::*;
use rand_distr::Exp;
use rand_pcg::Pcg64;
use simcore::simulation::Simulation;

mod balancer;
mod config;
mod events;
mod host;
mod log;

use crate::balancer::{create_selector_by_name, LoadBalancer};
use crate::config::Config;
use crate::events::{RequestArrivalEvent, SyncEvent};
use crate::host::Host;
use crate::log::EventLog;

#[derive(Parser, Debug)]
#[clap(about, long_about = None)]
struct Args {
    /// Results dump path.
    #[clap(long)]
    dump: String,

    /// Configuration JSON file.
    #[clap(long)]
    config: String,

    /// Number of servers.
    #[clap(long, default_value = "100")]
    servers: u32,

    /// Time limit in seconds.
    #[clap(long, default_value = "3600")]
    time_limit: f64,

    /// Number of senders generating requests.
    #[clap(long, default_value = "200")]
    senders: u32,

    /// Load distribution preset (balanced/skewed).
    #[clap(long, default_value = "balanced")]
    preset: String,

    /// Adds slower servers to simulate heterogenous cluster.
    #[clap(long)]
    different_servers: bool,

    /// Random seed.
    #[clap(long, default_value = "123")]
    seed: u64,
}

#[derive(Copy, Clone, PartialEq)]
struct RequestTime {
    pub time: f64,
    pub id: usize,
}

impl Eq for RequestTime {}

impl Ord for RequestTime {
    fn cmp(&self, other: &Self) -> Ordering {
        self.time
            .total_cmp(&other.time)
            .then(self.id.cmp(&other.id))
    }
}

impl PartialOrd for RequestTime {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

fn run_simulation(args: &Args, config: &Config) -> Vec<(f64, f64)> {
    let mut sim = Simulation::new(args.seed);
    let ctx = sim.create_context("entry point");
    let log = Rc::new(RefCell::new(EventLog::new()));
    let mut hosts = Vec::with_capacity(args.servers as usize);
    for i in 0..args.servers {
        let slowdown = if args.different_servers && i < args.servers / 20 {
            5.0
        } else {
            1.0
        };
        hosts.push(Rc::new(RefCell::new(Host::new(
            i as usize,
            slowdown,
            log.clone(),
            Rc::new(RefCell::new(sim.create_context(format!("host_{i}")))),
        ))));
        sim.add_handler(format!("host_{i}"), hosts[i as usize].clone());
    }
    let mut balancers = Vec::with_capacity(config.n_balancers as usize);
    for i in 0..config.n_balancers {
        balancers.push(Rc::new(RefCell::new(LoadBalancer::new(
            hosts.clone(),
            create_selector_by_name(&config.balancer),
            config.sync_interval,
            Rc::new(RefCell::new(sim.create_context(format!("balancer_{i}")))),
        ))));
        sim.add_handler(format!("balancer_{i}"), balancers[i as usize].clone());
        ctx.emit(SyncEvent {}, sim.lookup_id(&format!("balancer_{i}")), 0.0);
    }
    let mut rng = Pcg64::seed_from_u64(args.seed);
    let sim_limit = args.time_limit * 10.;
    for sender in 0..(args.senders as usize) {
        let distr = Exp::new(if args.preset == "skewed" && sender == 0 {
            50.0
        } else {
            1.0
        })
        .unwrap();
        let mut t = 0f64;
        loop {
            t += distr.sample(&mut rng) * 5.;
            if t > sim_limit {
                break;
            }
            let processing_time = rng.gen_range(0.5..2.5);
            ctx.emit(
                RequestArrivalEvent {
                    processing_time,
                    sender,
                },
                sim.lookup_id(&format!("balancer_{}", rng.gen_range(0..balancers.len()))),
                t,
            );
        }
    }
    sim.step_for_duration(sim_limit);
    for host in hosts {
        host.borrow_mut().flush(sim_limit);
    }
    let mut result = Vec::new();
    let mut evts = Vec::new();
    for entry in log.borrow().iter().copied() {
        evts.push((entry.1, entry.0 - entry.1));
    }
    evts.sort_by(|x, y| x.0.total_cmp(&y.0));
    let window = 60f64;
    let mut ptr = 0;
    let mut items = BTreeSet::new();
    let mut i = 0;
    while i < evts.len() && evts[i].0 <= args.time_limit {
        let start = evts[i].0;
        while ptr < evts.len() && evts[ptr].0 <= start + window {
            items.insert(RequestTime {
                time: evts[ptr].1,
                id: ptr,
            });
            ptr += 1;
        }
        let pos = (0.99 * (items.len() as f64)).trunc() as usize;
        result.push((
            start,
            items.iter().rev().nth(items.len() - 1 - pos).unwrap().time,
        ));
        while i < evts.len() && evts[i].0 == start {
            i += 1;
        }
    }
    result
}

fn main() {
    let args = Args::parse();
    let configs: Vec<Config> =
        serde_json::from_reader(File::open(Path::new(&args.config)).unwrap()).unwrap();
    let mut out = BufWriter::new(File::create(&args.dump).unwrap());
    for config in configs.iter() {
        let result = run_simulation(&args, config);
        out.write_all(config.balancer.as_bytes()).unwrap();
        out.write_all(b"\n").unwrap();
        out.write_all(
            result
                .iter()
                .map(|x| format!("{:.3}", x.0))
                .collect::<Vec<_>>()
                .join(",")
                .as_bytes(),
        )
        .unwrap();
        out.write_all(b"\n").unwrap();
        out.write_all(
            result
                .iter()
                .map(|x| format!("{}", x.1))
                .collect::<Vec<_>>()
                .join(",")
                .as_bytes(),
        )
        .unwrap();
        out.write_all(b"\n").unwrap();
    }
    out.flush().unwrap();
}
