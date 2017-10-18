import torch
import pickle
# import torch.nn as nn
# import torch.backends.cudnn as cudnn
from torch.autograd import Function
# from torch.autograd import Variable
# from ..box_utils import decode, nms
from .pytorch_box_utils import decode, nms
# from data import v2 as cfg
from .pytorch_parameters import v2 as cfg


class Detect(Function):
    """At test time, Detect is the final layer of SSD.  Decode location preds,
    apply non-maximum suppression to location predictions based on conf
    scores and threshold to a top_k number of output predictions for both
    confidence score and locations.
    """
    def __init__(self, num_classes, bkg_label, top_k, conf_thresh, nms_thresh):
        self.num_classes = num_classes
        self.background_label = bkg_label
        self.top_k = top_k
        # Parameters used in nms.
        self.nms_thresh = nms_thresh
        if nms_thresh <= 0:
            raise ValueError('nms_threshold must be non negative.')
        self.conf_thresh = conf_thresh
        self.variance = cfg['variance']
        self.output = torch.zeros(1, self.num_classes, self.top_k, 5)

    def forward(self, loc_data, conf_data, prior_data):
        """
        Args:
            loc_data: (tensor) Loc preds from loc layers
                Shape: [batch,num_priors*4]
            conf_data: (tensor) Shape: Conf preds from conf layers
                Shape: [batch*num_priors,num_classes]
            prior_data: (tensor) Prior boxes and variances from priorbox layers
                Shape: [1,num_priors,4]
        """
        num = loc_data.size(0)  # batch size
        num_priors = prior_data.size(0)
        self.output.zero_()
        if num == 1:
            # size batch x num_classes x num_priors
            conf_preds = conf_data.t().contiguous().unsqueeze(0)
        else:
            conf_preds = conf_data.view(num, num_priors,
                                        self.num_classes).transpose(2, 1)
            self.output.expand_(num, self.num_classes, self.top_k, 5)

        # Decode predictions into bboxes.
        class_selections = []
        for i in range(num):
            decoded_boxes = decode(loc_data[i], prior_data, self.variance)
            # For each class, perform nms
            conf_scores = conf_preds[i].clone()
            num_det = 0
            for cl in range(1, self.num_classes):
                c_mask = conf_scores[cl].gt(self.conf_thresh)
                scores = conf_scores[cl][c_mask]
                if scores.dim() == 0:
                    continue
                l_mask = c_mask.unsqueeze(1).expand_as(decoded_boxes)
                boxes = decoded_boxes[l_mask].view(-1, 4)
                # idx of highest scoring and non-overlapping boxes per class
                pickle.dump(boxes, open('torch_boxes.pkl', 'wb'))
                pickle.dump(scores, open('torch_scores.pkl', 'wb'))

                ids, count = nms(boxes, scores, self.nms_thresh, self.top_k)
                selections = torch.cat((scores[ids[:count]].unsqueeze(1),
                                        boxes[ids[:count]]), 1)

                class_selections.append(selections.numpy())
                # pickle.dump(selections, open('torch_selections.pkl', 'wb'))
                """
                self.output[i, cl, :count] = \
                    torch.cat((scores[ids[:count]].unsqueeze(1),
                               boxes[ids[:count]]), 1)
                """
                # print('torch_selections:', selections.numpy())
                print('torch class', cl)
                print('torch count', count)
                self.output[i, cl, :count, :] = selections

        pickle.dump(class_selections, open('torch_selections.pkl', 'wb'))
        pickle.dump(self.output, open('torch_output.pkl', 'wb'))
        return self.output
        """
        a = self.output
        flt = self.output.view(-1, 5)
        _, idx = flt[:, 0].sort(0)
        _, rank = idx.sort(0)
        flt[(rank >= self.top_k).unsqueeze(1).expand_as(flt)].fill_(0)
        print(a == self.output)
        """
        return self.output