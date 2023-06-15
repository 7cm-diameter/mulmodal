library(tidyverse)
library(comprexr)

LICKL <- -10
LICKR <- -9
REWARDL <- 2
REWARDR <- 3
LIGHTL <- 8
LIGHTLC <- 7
LIGHTC <- 6
LIGHTRC <- 5
LIGHTR <- 4
LIGHTS <- c(LIGHTL, LIGHTLC, LIGHTC, LIGHTRC, LIGHTR)


rawdata <- list.files("./mulmodal/data", pattern = "multi", full.names = T) %>%
  lapply(., function(path) {
    read.csv(path) %>%
      mutate(time = time - min(time)) %>%
      add_metadata_to_df(., path) %>%
      mutate(light = as.numeric(.$event %in% LIGHTS))
}) %>% do.call(rbind, .)

raster_light_all <- rawdata %>%
  split(., list(.$subject, .$date), drop = T) %>%
  lapply(., function(d) {
    d %>%
      filter(event %in% c(LICKL, LICKR, REWARDL, REWARDR, LIGHTS)) %>%
      align_with(., "light", 1, "time", -3, 3) %>%
      filter(event == LICKR)
}) %>%
  do.call(rbind, .)

ggplot(raster_light_all) +
  geom_point(aes(x = time, y = serial),
             size = .75, alpha = .75) +
  geom_vline(xintercept = 0,
             color = "orange", linetype = "dashed", size = 1.5) +
  geom_vline(xintercept = 1,
             color = "skyblue", linetype = "dashed", size = 1.5) +
  ylim(0, 120) +
  xlab("Time from cue onsets") +
  ylab("Trial") +
  facet_grid(~subject~date) +
  theme_bw() +
  theme(aspect.ratio = 1)

raster_light_each <- rawdata %>%
  filter(date == "230612") %>%
  split(., list(.$subject, .$date), drop = T) %>%
  lapply(., function(d) {
    d <- d %>%
      filter(event %in% c(LICKL, LICKR, LIGHTS))
    lapply(LIGHTS, function(light_position) {
      d_<- align_with(d, "event", light_position, "time", -3, 3) %>%
        mutate(light_position = light_position)
    }) %>%
      do.call(rbind, .) %>%
      filter(event %in% c(LICKL, LICKR))
}) %>%
  do.call(rbind, .)


ggplot(raster_light_each) +
  geom_point(aes(x = time, y = serial),
             size = .75, alpha = .75) +
  geom_vline(xintercept = 0,
             color = "orange", linetype = "dashed", size = 1.5) +
  geom_vline(xintercept = 1,
             color = "skyblue", linetype = "dashed", size = 1.5) +
  xlab("Time from cue onsets") +
  ylab("Trial") +
  facet_grid(~subject~date+light_position) +
  theme_bw() +
  theme(aspect.ratio = 1)

lick_in_window <- raster_light_all %>%
  split(., list(.$subject, .$date), drop = T) %>%
  lapply(., function(d) {
    trial <- max(d$serial)
    before_CS <- d %>% filter(time <= 0.) %>% (function(d_) nrow(d_) / (3. * trial))
    during_CS <- d %>% filter(time > 0., time <= 1.) %>% (function(d_) nrow(d_) / trial)
    after_CS <- d %>% filter(time > 1.) %>% (function(d_) nrow(d_) / (2. * trial))
    data.frame(subject = unique(d$subject),
               date = unique(d$date) %>% as.numeric,
               lick = c(before_CS, during_CS, after_CS),
               ratio = c(before_CS / before_CS, during_CS / before_CS, after_CS / before_CS),
               window = c("Before", "During", "After"))
  }) %>%
  do.call(rbind, .)

ggplot(lick_in_window
        %>% filter(window == "During")
      ) +
  geom_line(aes(x = date, y = ratio),
             size = 1.5) +
  geom_point(aes(x = date, y = ratio),
             size = 5) +
  geom_point(aes(x = date, y = ratio),
             size = 3, color = "white") +
  xlab("Date") +
  ylab("CR ratio (During CS : Before CS)") +
  facet_wrap(~subject, scales = "free", ncol = 1) +
  theme(aspect.ratio = .75)
