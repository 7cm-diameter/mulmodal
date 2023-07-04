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
NOISE <- 14


rawdata <- list.files("./mulmodal/data", pattern = "sound", full.names = T) %>%
  lapply(., function(path) {
    read.csv(path) %>%
      mutate(time = time - min(time)) %>%
      add_metadata_to_df(., path)
}) %>% do.call(rbind, .)

raster_sound <- rawdata %>%
  split(., list(.$subject, .$date), drop = T) %>%
  lapply(., function(d) {
    d %>%
      filter(event %in% c(LICKL, LICKR, REWARDL, REWARDR, LIGHTS, NOISE)) %>%
      align_with(., "event", NOISE, "time", -3, 3)
}) %>%
  do.call(rbind, .)

ggplot(raster_sound %>% filter(date == "230701", event %in% c(LICKL, LICKR))) +
  geom_point(aes(x = time, y = serial),
             size = 1., alpha = .75) +
  geom_vline(xintercept = 0,
             color = "orange", linetype = "dashed", size = 1.5) +
  geom_vline(xintercept = 1,
             color = "skyblue", linetype = "dashed", size = 1.5) +
  ylim(0, 120) +
  xlab("Time from cue onsets") +
  ylab("Trial") +
  facet_grid(~subject) +
  theme_bw() +
  theme(aspect.ratio = 1)
